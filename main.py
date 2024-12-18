import os
import time
import ntptime
from time import sleep
import uasyncio
from machine import Pin
from WiFiConnection import WiFiConnection
from microdot.microdot import Microdot
from microdot.microdot import send_file
from microdot.sse import with_sse
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
boost_timer_add = 900 # timer increase in seconds (15 minutes)
boost_timer_countdown = 0 # timer in seconds
boost_pressed = 0

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

app = Microdot()

# root route handler
@app.get('/')
async def index(request):
    return send_file('/index.html')

@app.get('/heating.js')
async def js(request):
    return send_file('/heating.js')

@app.route('/events')
@with_sse
async def events(request, sse):
    # Stream status to client every second
    last_response_obj = {}
    while True:
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
        if response_obj != last_response_obj:
            last_response_obj = response_obj
            await sse.send(response_obj)
            
        # Pause between sending again
        await uasyncio.sleep(1)

# Alternate GET api just returns status
@app.get('/api')
async def api_get(request):
    current_day = time.localtime()[6] + 1
    current_time = (time.localtime()[3] * 60) + time.localtime()[4]
    # Return current time, heating and timers status
    response_obj = {
        'status': 'OK',
        'current_day': current_day,
        'current_time': current_time,
        'heating_state': heating_state,
        'is_heating': is_heating,
        'boost_timer_countdown': boost_timer_countdown,
        'timers': timers
    }
    return response_obj

# Essentially a basic REST api for settings - POST only, to one end point
@app.post('/api')
async def api_post(request):
    global heating_state
    global boost_pressed
    global boost_timer_countdown
    global timers
    
    action = request.json["action"]
    if action == 'get_status':
        current_day = time.localtime()[6] + 1
        current_time = (time.localtime()[3] * 60) + time.localtime()[4]
        # Return current time, heating and timers status
        response_obj = {
            'status': 'OK',
            'current_day': current_day,
            'current_time': current_time,
            'heating_state': heating_state,
            'is_heating': is_heating,
            'boost_timer_countdown': boost_timer_countdown,
            'timers': timers
        }
        return response_obj
    elif action == "boost":
        # Execute a manual heating 'boost' timer
        if boost_timer_countdown == 0:
            boost_pressed = 1
            boost_timer_countdown = boost_timer
            heating_state = True # Boost will also enable the heating
        else:
            # Subsequent pushes of the boost button will increase boost timer by 15 minutes until 3 pushes
            if boost_pressed < 3:
                boost_timer_countdown += boost_timer_add
                boost_pressed += 1
            else:
                boost_pressed = 0
                boost_timer_countdown = 0
        
        response_obj = {
            'status': 'OK',
            'boost_timer_countdown': boost_timer_countdown
        }
        return response_obj
    elif action == 'trigger_heating':
        # Permanently turn heating off (holiday mode) or on
        heating_state = not heating_state
        
        response_obj = {
            'status': 'OK',
            'heating_state': heating_state
        }
        return response_obj
    elif action == "set_timer":
        # Change a timer days and on/off time (minutes of day)
        error_message = ""
        timer_number = request.json['timer_number']
        new_days = int(request.json['new_days'])
        new_on_time = int(request.json['new_on_time'])
        new_off_time = int(request.json['new_off_time'])
        # Validate inputs
        if timer_number < 1 or timer_number > 6:
            error_message = "Invalid timer number"
        elif new_days < 0 or new_days > 127:
            error_message = "Invalid timer days"
        elif new_on_time < 0 or new_on_time > 1410:
            error_message = "Invalid on time"
        elif new_off_time < 0 or new_off_time > 1410:
            error_message = "Invalid off time"
        else:
            timers[timer_number - 1][0] = new_days
            timers[timer_number - 1][1] = new_on_time
            timers[timer_number - 1][2] = new_off_time
            save_data()
            response_obj = {
                'status': 'OK',
                'timer_number': timer_number,
                'new_days': new_days,
                'new_on_time': new_on_time,
                'new_off_time': new_off_time
            }
            return response_obj
        if error_message != "":
            response_obj = {
                'status': 'ERROR',
                'message': error_message
            }
            return response_obj, 400
    else:
        response_obj = {
                'status': 'ERROR',
                'message': "Unknown action"
            }
        return response_obj, 400

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
                    if current_time >= timer[1] and current_time < timer[2]:
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

    updated_today = False

    # start web server task
    print('Setting up webserver...')
    uasyncio.create_task(app.start_server(debug=False, port=80))

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
