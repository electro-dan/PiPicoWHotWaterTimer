# class to handle WiFi conenction
import utime
import network
import secrets

class WiFiConnection:
    # class level vars accessible to all code
    status = network.STAT_IDLE
    ip = ""
    subnet_mask = ""
    gateway = ""
    dns_server = ""
    wlan = None

    def __init__(self):
        pass


    @classmethod
    def do_connect(self, print_progress=False):
        network.hostname("water")
        # set WiFi to station interface
        self.wlan = network.WLAN(network.STA_IF)
        # activate the network interface
        self.wlan.active(True)
        # connect to wifi network
        self.wlan.connect(secrets.SSID, secrets.PASSWORD)
        self.status = network.STAT_CONNECTING
        if print_progress:
            print("Connecting to Wi-Fi - please wait")
        max_wait = 20
        # wait for connection - poll every 0.5 secs
        while max_wait > 0:
            """
                0   STAT_IDLE -- no connection and no activity,
                1   STAT_CONNECTING -- connecting in progress,
                -3  STAT_WRONG_PASSWORD -- failed due to incorrect password,
                -2  STAT_NO_AP_FOUND -- failed because no access point replied,
                -1  STAT_CONNECT_FAIL -- failed due to other problems,
                3   STAT_GOT_IP -- connection successful.
            """
            if self.wlan.status() < 0 or self.wlan.status() >= 3:
                # connection attempt finished
                break
            max_wait -= 1
            utime.sleep(0.5)

        # check connection
        self.status = self.wlan.status()
        if self.wlan.status() != 3:
            # No connection
            if print_progress:
                print("Connection Failed")
            return False
        else:
            # connection successful
            config = self.wlan.ifconfig()
            self.ip = config[0]
            self.subnet_mask = config[1]
            self.gateway = config[2]
            self.dns_server = config[3]
            if print_progress:
                print('ip = ' + str(self.ip))
            return True

    @classmethod
    def is_connected(cls):
        if cls.wlan:
            return cls.wlan.isconnected()
        else:
            return False
    
