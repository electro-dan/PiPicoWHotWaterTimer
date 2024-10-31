import os
import time
import ntptime
from time import sleep
import uasyncio
from machine import Pin
from RequestParser import RequestParser
from ResponseBuilder import ResponseBuilder
from WiFiConnection import WiFiConnection
from machine import WDT
from machine import Timer

# Watchdog timer - set to 8 seconds to allow enough time for WiFi connect attempts
# Will reset the Pico if unresponsive after 8 seconds. Use wdt.feed() to indicate 'alive'
#wdt = WDT(timeout=8000) #timeout is in ms

# heating trigger pin
heating_pin_trig = Pin(28, Pin.OUT)
heating_pin_hold = Pin(27, Pin.OUT)
# manual boost button
boost_pin = Pin(18, Pin.IN, Pin.PULL_UP)
button_state = 0xFFFF

is_heating = False # Default to off
heating_state = True # Default to on
boost_timer = 1800 # timer in seconds (30 minutes)
boost_timer_countdown = 0 # timer in seconds

# list of timers
# timer list contains days (bitmask of 127), on time in minutes, off time in minutes
timers = [
    [127, 450, 390],
    [0, 420, 420],
    [0, 420, 420],
    [0, 420, 420],
    [0, 420, 420],
    [0, 420, 420]
]

# coroutine to handle HTTP request
async def handle_request(reader, writer):
    global heating_state
    global boost_timer_countdown
    global timers
    try:
        # await allows other tasks to run while waiting for data
        raw_request = await reader.read(2048)

        request = RequestParser(raw_request)

        response_builder = ResponseBuilder()

        # filter out api request
        if request.url_match("/api"):
            action = request.get_action()
            if action == 'get_status':
                current_day = time.localtime()[6] + 1
                current_time = (time.localtime()[3] * 60) + time.localtime()[4]
                response_obj = {
                    'status': 'OK',
                    'current_day': current_day,
                    'current_time': current_time,
                    'heating_state': heating_state,
                    'is_heating': is_heating,
                    'boost_timer_countdown': boost_timer_countdown,
                    'timers': timers
                }
                response_builder.set_body_from_dict(response_obj)
            elif action == "boost":
                if boost_timer_countdown == 0:
                    boost_timer_countdown = boost_timer
                else:
                    boost_timer_countdown = 0
                
                response_obj = {
                    'status': 'OK',
                    'boost_timer_countdown': boost_timer_countdown
                }
                response_builder.set_body_from_dict(response_obj)
            elif action == 'trigger_heating':
                # Permanently turn heating off (holiday mode) or on
                heating_state = not heating_state
               
                response_obj = {
                    'status': 'OK',
                    'heating_state': heating_state
                }
                response_builder.set_body_from_dict(response_obj)
            elif action == "set_timer":
                # Set off time
                timer_number = request.data()['timer_number']
                on_or_off = request.data()['on_or_off']
                new_time = int(request.data()['new_time'])
                if new_time >= 0 and new_time <= 1410:
                    if on_or_off == "On":
                        timers[timer_number - 1][1] = new_time
                    else:
                        timers[timer_number - 1][2] = new_time
                    save_data()
                    response_obj = {
                        'status': 'OK',
                        'timer_number': timer_number,
                        'time_set': new_time
                    }
                    response_builder.set_body_from_dict(response_obj)
                else:
                    response_obj = {
                        'status': 'ERROR',
                        'message': "Invalid time sent"
                    }
                    response_builder.set_body_from_dict(response_obj)
                    response_builder.set_status(400)
            elif action == "set_timer_days":
                # Set off time
                timer_number = int(request.data()['timer_number'])
                timer_day = int(request.data()['day'])
                if timer_day >= 0 and timer_day <= 7:
                    # mask with the nth bit set
                    timer_day_mask = 1 << (timer_day - 1)
                    current_timer_days = timers[timer_number - 1][0]
                    # toggle the bit with xor
                    new_timer_days = current_timer_days ^ timer_day_mask
                    timers[timer_number - 1][0] = new_timer_days
                    save_data()
                    response_obj = {
                        'status': 'OK',
                        'timer_number': timer_number,
                        'new_timer_days': new_timer_days
                    }
                    response_builder.set_body_from_dict(response_obj)
                else:
                    response_obj = {
                        'status': 'ERROR',
                        'message': "Invalid time sent"
                    }
                    response_builder.set_body_from_dict(response_obj)
                    response_builder.set_status(400)


            else:
                # unknown action
                response_builder.set_status(404)

        # try to serve static file
        else:
            response_builder.serve_static_file(request.url, "/index.html")

        # build response message
        response_builder.build_response()
        # send response back to client
        writer.write(response_builder.response)
        # allow other tasks to run while data being sent
        await writer.drain()
        await writer.wait_closed()

    except OSError as e:
        print('connection error ' + str(e.errno) + " " + str(e))

# Main timer interrupt - runs every second
# This will activate / deactivate hot water based on whether the local time is within an active timer
def timer_check_interrupt(pin):
    global heating_state
    global is_heating
    global timers
    global boost_timer_countdown

    # Convert local time into minutes since midnight
    current_day = time.localtime()[6] + 1
    current_time = (time.localtime()[3] * 60) + time.localtime()[4]
    # Iterate through timers
    is_heating = False
    # If heating is enabled
    if heating_state:
        for timer in timers:
            # if timer is enabled for today (bitwise AND)
            if current_day & timer[0]:
                # If the on and off timer are not the same
                if timer[1] != timer[2]:
                    # If the current time is between the on and off times, enable heating
                    if current_time > timer[1] and current_time < timer[2]:
                        is_heating = True

        if boost_timer_countdown > 0:
            is_heating = True
            boost_timer_countdown -= 1 # take off 1 second

def relay_timer_interrupt(pin):
    # Enable or disable the output
    if is_heating:
        # Run hold first - this will switch the relay into hold state if last run was to activate
        do_relay_hold()
        # This will activate the relay if it is off or not in hold state
        do_relay_activate()
    else:
        do_relay_deactivate()

# This function runs constantly and polls the push button with debounce handling
# It shifts the button status into a variable (capped at 16-bits) and compares to a mask
# Result is this function reliably detects a valid push, without triggering multiple times
async def button_handler():
    global is_heating
    global button_state

    while True:
        # based on https://www.e-tinkers.com/2021/05/the-simplest-button-debounce-solution/
        button_state = ((button_state << 1) | boost_pin.value() | 0xfe00) & 0xFFFF

        # Check button
        if button_state == 0xFF00:
            do_boost()
        
        await uasyncio.sleep_ms(5)

# main coroutine to boot async tasks
async def main():
    # Start the timer task
    print('Starting hardware...')
    uasyncio.create_task(button_handler())

    # start web server task
    print('Setting up webserver...')
    server = uasyncio.start_server(handle_request, "0.0.0.0", 80)
    uasyncio.create_task(server)

    updated_today = False

    while True:
        # This loop just monitors the WiFi connection and tries re-connects if disconnected
        # Connect to WiFi if disconnected
        if not WiFiConnection.is_connected():
            # try to connect again
            print('WiFi connect...')
            if WiFiConnection.do_connect(True):
                # Time will be in UTC only
                try:
                    ntptime.settime()
                except:
                    print("NTP timeout")
                finally:
                    print(time.localtime())
        else:
            # After midnight, update NTP time once a day
            if time.localtime()[3] == 0:
                if not updated_today:
                    try:
                        ntptime.settime()
                        updated_today = True
                    except:
                        print("NTP timeout")
                    finally:
                        print(time.localtime())
            else:
                updated_today = False

        await uasyncio.sleep_ms(2000)

        #wdt.feed() # Reset watchdog

# Activates the override boost timer
def do_boost():
    global boost_timer_countdown
    # If button is still pressed
    if not boost_pin.value():
        # Set or reset boost countdown
        if boost_timer_countdown == 0:
            boost_timer_countdown = boost_timer
        else:
            boost_timer_countdown = 0
    
# Used to activate the relay
def do_relay_activate():
    if heating_pin_hold.value() == 0 & heating_pin_trig.value() == 0:
        heating_pin_hold.value(0)
        heating_pin_trig.value(1)
        return True
    else:
        return False

# Used to hold relay after activating
def do_relay_hold():
    if heating_pin_trig.value() == 1:
        heating_pin_hold.value(1)
        heating_pin_trig.value(0)

# Used to deactivate the relay
def do_relay_deactivate():
    heating_pin_hold.value(0)
    heating_pin_trig.value(0)

# Save variables to the eeprom
def save_data():
    print('Saving variables...')
    with open('config.txt', 'w') as f:
        for timer in timers:
            str_data = str(timer[0]) + "|" + str(timer[1]) + "|" + str(timer[2]) + "\n"
            f.write(str_data)

# Read variables from the eeprom - done at boot
def read_data():
    global timers

    with open('config.txt', 'r') as f:
        file_lines = f.readlines()
 
        count = 0
        # Strips the newline character
        for file_line in file_lines:
            timer_list = file_line.strip().split('|')
            if len(timer_list) == 3:
                if count < 7:
                    timers[count][0] = int(timer_list[0])
                    timers[count][1] = int(timer_list[1])
                    timers[count][2] = int(timer_list[2])
                count += 1

# Entry Here
# Read any existing saved data
read_data()

# Start a timer to interrupt every 1 second
timer_check = Timer(mode=Timer.PERIODIC, period=1000, callback=timer_check_interrupt)
# Start a timer to interrupt every 300 milliseconds
relay_timer = Timer(mode=Timer.PERIODIC, period=300, callback=relay_timer_interrupt)

# start asyncio task and loop
try:
    # start the main async tasks
    uasyncio.run(main())
finally:
    # reset and start a new event loop for the task scheduler
    uasyncio.new_event_loop()
