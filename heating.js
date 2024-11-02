var isChanging = false;
var changingTimeout;

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
            if (!isChanging) {
                const timerArr = json_response.timers;
                var timer = 1;
                for (var i = 0; i < timerArr.length; i++) {
                    timer = i + 1;
                    // Only set control if it is disabled (not editing)
                    if (document.getElementById("t" + timer + "Day1").disabled) {
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
            if (json_response.boost_timer_countdown != "0") {
                setTimeout(getStatus, 450);
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
            setTimeout(getStatus, 450);
        } else {
            alert("Error setting target temperature");
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

function editTimer(timer) {
    // Check state of a control
    if (document.getElementById("t" + timer + "Day1").disabled) {
        // Enable controls
        toggleControlsDisabled(timer, false);
        // Show cancel button
        document.getElementById("btnC" + timer).style.display="block";
        // Change to save icon
        document.getElementById("btnT" + timer).innerHTML = "&#x1F4BE;";
    } else {
        startChange();

        var newDays = 0;
        var daysTest = 1;
        // Loop from 1 to 7 - 1 = Monday
        for (var i = 1; i < 8; i++) {
            // If the day is checked, add on the test byte
            if (document.getElementById("t" + timer + "Day" + i).checked)
                newDays += daysTest;
            daysTest <<= 1; // Shift bit left in the test byte
        }

        // Apply the changes
        const jsonData = {
            "action": "set_timer",
            "timer_number": timer,
            "new_days": newDays,
            "new_on_time": document.getElementById("t" + timer + "OnInput").value,
            "new_off_time": document.getElementById("t" + timer + "OffInput").value
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
                //checkTimerDayBoxes(timer, newTimerDays);
            } else {
                alert("Error setting timer - " + json_response.message);
            }
        }
        xhttp.open("POST", "/api", true);
        xhttp.setRequestHeader("Content-Type", "application/json;charset=UTF-8");
        xhttp.send(JSON.stringify(jsonData));

        // Disable controls
        toggleControlsDisabled(timer, true);
        // Change to edit icon
        document.getElementById("btnT" + timer).innerHTML = "&#x1F589;";
        // Hide cancel button
        document.getElementById("btnC" + timer).style.display="none";
        endChange();
    }
}

function cancelTimer(timer) {
    // Disable controls
    toggleControlsDisabled(timer, true);
    // Change to edit icon
    document.getElementById("btnT" + timer).innerHTML = "&#x1F589;";
    // Hide cancel button
    document.getElementById("btnC" + timer).style.display="none";
    // Get original status
    getStatus();
}

function toggleControlsDisabled(timer, isDisabled) {
    // Loop from 1 to 7 - 1 = Monday
    for (var i = 1; i < 8; i++) {
        // If the bit in newTimerDays is the same bit set in bMask, then check the box
        document.getElementById("t" + timer + "Day" + i).disabled = isDisabled;
    }
    // On time
    document.getElementById("t" + timer + "OffInput").disabled = isDisabled;
    // On time
    document.getElementById("t" + timer + "OnInput").disabled = isDisabled;
}

// Read status when page is focused
window.onfocus = function() {
    getStatus();
}
getStatus();

