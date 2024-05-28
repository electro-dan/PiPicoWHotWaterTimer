var isChanging = false;
var changingTimeout;
var statusInterval;

// Called on load, then every second
function getStatus() {
    const formData = new FormData();
    formData.append("action", "get_status");
    // Post back to the python service
    const xhttp = new XMLHttpRequest();
    xhttp.onload = function() {
        var json_response = JSON.parse(this.responseText);
        console.log(json_response);

        if (json_response.status == "OK") {
            var dayOfWeek = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
            document.getElementById("localTime").innerHTML = dayOfWeek[json_response.current_day - 1] + " " + formatTime(json_response.current_time) + " UTC";
            document.getElementById("boostTimer").innerHTML = formatCountdown(json_response.boost_timer_countdown);
            document.getElementById("heatingState").innerHTML = (json_response.heating_state ? "ENABLED" : "DISABLED");
            document.getElementById("isHeating").innerHTML = (json_response.is_heating ? "ON" : "OFF");
            if (json_response.boost_timer_countdown == 0)
                clearInterval(statusInterval);
            if (!isChanging) {
                const timerArr = json_response.timers;
                var timer = 1;
                for (var i = 0; i < timerArr.length; i++) {
                    timer = i + 1;
                    // Days
                    checkTimerDayBoxes(timer, timerArr[i][0]);
                    // On time
                    document.getElementById("t" + timer + "On").innerHTML = formatTime(timerArr[i][1]);
                    document.getElementById("t" + timer + "OnInput").value = timerArr[i][1];
                    // Off time
                    document.getElementById("t" + timer + "Off").innerHTML = formatTime(timerArr[i][2]);
                    document.getElementById("t" + timer + "OffInput").value = timerArr[i][2];
                }
            }
        }
    }
    xhttp.open("POST", "/api", true);
    xhttp.send(formData);
}

// Functions to prevent the interval reseting displayed values when changing a control
function resetChanging() {
    isChanging = false;
}

function startChange() {
    clearTimeout(changingTimeout);
    isChanging = true;
}

function timeoutChange() {
    changingTimeout = setTimeout(resetChanging, 10000);
}

function endChange() {
    changingTimeout = setTimeout(resetChanging, 1000);
}

// Global heating enable/disable
function triggerHeating() {
    const jsonData = {
        "action": "trigger_heating"
    };
    // Post back to the python service
    const xhttp = new XMLHttpRequest();
    xhttp.onload = function() {
        var json_response = JSON.parse(this.responseText);
        console.log(json_response);

        if (json_response.status == "OK") {
            // reset led indicator to none
            document.getElementById("heatingState").innerHTML = (json_response.heating_state ? "ENABLED" : "DISABLED");
        } else {
            alert("Error setting heating state");
        }

    }
    xhttp.open("POST", "/api", true);
    xhttp.setRequestHeader("Content-Type", "application/json;charset=UTF-8");
    xhttp.send(JSON.stringify(jsonData));
}

// Set the target temperature
function triggerBoost() {
    startChange();

    const jsonData = {
        "action": "boost"
    };
    // Post back to the python service
    const xhttp = new XMLHttpRequest();
    xhttp.onload = function() {
        var json_response = JSON.parse(this.responseText);
        console.log(json_response);

        if (json_response.status == "OK") {
            // reset led indicator to none
            document.getElementById("boostTimer").innerHTML = formatCountdown(json_response.boost_timer_countdown);
            // Get the status every second whilst boost is active
            statusInterval = setInterval(getStatus, 1000);
        } else {
            alert("Error setting target temperature");
        }
    }
    xhttp.open("POST", "/api", true);
    xhttp.setRequestHeader("Content-Type", "application/json;charset=UTF-8");
    xhttp.send(JSON.stringify(jsonData));

    endChange();
}

// This function is used when the control is released - the result is saved
function setDay(timer, day) {
    startChange();

    // Toggle a day for the given timer
    const jsonData = {
        "action": "set_timer_days",
        "timer_number": timer,
        "day": day
    };
    // Post back to the python service
    const xhttp = new XMLHttpRequest();
    xhttp.onload = function() {
        var json_response = JSON.parse(this.responseText);
        console.log(json_response);

        if (json_response.status == "OK") {
            // set the checkboxes
            newTimerDays = json_response.new_timer_days
            // Check the boxes based on the new set timer days
            checkTimerDayBoxes(timer, newTimerDays);
        } else {
            alert("Error setting on/off time");
        }
    }
    xhttp.open("POST", "/api", true);
    xhttp.setRequestHeader("Content-Type", "application/json;charset=UTF-8");
    xhttp.send(JSON.stringify(jsonData));

    endChange();
}

function checkTimerDayBoxes(timer, newTimerDays) {
    // Based on the binary days setting, check or uncheck each day checkbox
    bMask = 1; // Mask starts at 1, and is then left shifted in the loop
    // Loop from 1 to 7 - 1 = Monday
    for (var i = 1; i < 8; i++) {
        // If the bit in newTimerDays is the same bit set in bMask, then check the box
        document.getElementById("t" + timer + "Day" + i).checked = newTimerDays & bMask;
        // Shift the mask bit left each time (zero filled from the right)
        bMask = bMask << 1;
    }
}

function setTime(timer, onOrOff) {
    startChange();

    // Set an on or off time HH:MM based on the slider control for the relevant timer
    const jsonData = {
        "action": "set_timer",
        "timer_number": timer,
        "on_or_off": onOrOff,
        "new_time": document.getElementById("t" + timer + onOrOff + "Input").value
    };
    // Post back to the python service
    const xhttp = new XMLHttpRequest();
    xhttp.onload = function() {
        var json_response = JSON.parse(this.responseText);
        console.log(json_response);

        if (json_response.status == "OK") {
            // reset led indicator to none
            document.getElementById("t" + timer + onOrOff).innerHTML = formatTime(json_response.time_set);
        } else {
            alert("Error setting on/off time");
        }
    }
    xhttp.open("POST", "/api", true);
    xhttp.setRequestHeader("Content-Type", "application/json;charset=UTF-8");
    xhttp.send(JSON.stringify(jsonData));

    endChange();
}

// This function is used when the control slider is dragged
function moveTime(timer, onOrOff) {
    startChange();
    document.getElementById("t" + timer + onOrOff).innerHTML = formatTime(document.getElementById("t" + timer + onOrOff + "Input").value);
    timeoutChange();
}

// Used by above functions to format the set time into 12h format hh:mm
function formatTime(timeIn) {
    var hour = Math.floor(timeIn / 60)
    var ampm = " AM"
    if (hour > 11)
        ampm = " PM"
    if (hour > 12)
        hour -= 12
    return String(hour) + ":" + String(timeIn % 60).padStart(2, "0") + ampm;
}

// Used by above functions to format the boost countdown into mm:ss format
function formatCountdown(countdownIn) {
    return String(Math.floor(countdownIn / 60)).padStart(2, "0") + ":" + String(countdownIn % 60).padStart(2, "0");
}

//setInterval(getStatus, 1000);
// Read status when page is focused
window.onfocus = function() {
    getStatus();
}
getStatus();

