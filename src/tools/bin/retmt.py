#!/usr/bin/env python3

import os
import subprocess
from datetime import datetime
import re

# Installation constants
XyDisp = os.getenv('XYMSRV')  # Name of monitor server
XySend = os.getenv('XYMON')  # Monitor interface program
FmtDate = os.getenv('XYMONDATEFORMAT', '%Y.%m.%d %H:%M:%S')  # Default date format

if not XyDisp:
    raise EnvironmentError("Environment variable XYMSRV is not set.")
if not XySend:
    raise EnvironmentError("Environment variable XYMON is not set.")

HostName = subprocess.check_output('hostname', shell=True).decode().strip()  # 'Source' of this test
TestName = 'env'  # Test name
ThresholdYellow = 60  # Warning threshold [C]
ThresholdRed = 70  # Error threshold [C]

ColourOf = ['red', 'yellow', 'clear', 'green']

CpuFil = '/sys/class/thermal/thermal_zone0/temp'
GpuCmd = '/usr/bin/vcgencmd measure_temp'

# Global variables
Now = datetime.now().strftime(FmtDate)
Colour = 3  # Test status
Result = ''  # Message to sent to Xymon
Temp = {}  # Temperature readings

ErrMsg = {colour: [] for colour in ColourOf}  # Error messages

def log_message(msg):
    time_now = datetime.now()
    print(f"{time_now.year:04d}{time_now.month:02d}{time_now.day:02d} {time_now.hour:02d}{time_now.minute:02d}{time_now.second:02d} {msg}")

def max(a, b):
    return a if a > b else b

def min(a, b):
    return a if a < b else b

def inform_xymon():
    global Result, Colour, ErrMsg

    ErrMsg_str = ''
    for i, clr in enumerate(ColourOf):
        if ErrMsg[clr]:
            Colour = min(Colour, i)
            ErrMsg_str += f"&{clr} " + "\n&".join(ErrMsg[clr]) + "\n"

    if ErrMsg_str:
        ErrMsg_str += "\n"

    Colour = ColourOf[Colour]
    Result = f"status {HostName}.{TestName} {Colour} {Now}\n" \
              f"<b>Temperature sensor readings</b>\n\n" \
              f"{ErrMsg_str}{Result}\n"

    subprocess.run([XySend, XyDisp, Result], check=True)

    Result = ''
    Colour = 3
    for colour in ColourOf:
        ErrMsg[colour] = []

def read_sensors():
    global Temp

    Temp.clear()

    try:
        with open(CpuFil, 'r') as f:
            lines = f.readlines()
            if len(lines) == 1 and lines[0].startswith(('0', '1', '2', '3', '4', '5', '6', '7', '8', '9')):
                temp_value = float(lines[0].strip()) / 1000
                Temp['CPU'] = {
                    'label': 'CPU',
                    'input': temp_value,
                    'max': ThresholdYellow,
                    'crit': ThresholdRed
                }
            else:
                ErrMsg['clear'].append(f"Cannot read CPU temperature from {CpuFil}:\nUnexpected input")
    except OSError as e:
        ErrMsg['clear'].append(f"Cannot read CPU temperature from {CpuFil}:\n{e}")

    try:
        lines = subprocess.check_output(GpuCmd, shell=True).decode().strip().splitlines()
        if len(lines) == 1 and 'temp=' in lines[0]:
            match = re.match(r'^temp=(\d+\.\d+).*C$', lines[0])
            if match:
                temp_value = float(match.group(1))
                Temp['GPU'] = {
                    'label': 'GPU',
                    'input': temp_value,
                    'max': ThresholdYellow,
                    'crit': ThresholdRed
                }
            else:
                ErrMsg['clear'].append(f"Cannot read GPU temperature from `{GpuCmd}`:\nUnexpected input : {lines[0]}")
        else:
            ErrMsg['clear'].append(f"Cannot read GPU temperature from `{GpuCmd}`:\nno data returned")
    except subprocess.CalledProcessError as e:
        ErrMsg['clear'].append(f"Cannot read GPU temperature from `{GpuCmd}`:\n{e}")

def build_message():
    global Result, Temp

    if not Temp:
        Result = "No data received\n"
        return

    TempMin = 100
    TempAvg = 0
    TempMax = -100

    Result = "<table border=1 cellpadding=5>\n" \
             " <tr> <th>Sensor</th> <th>Temp [C]</th> <th>Threshold [C]</th> </tr>\n"

    for sensor, data in Temp.items():
        TempMin = min(TempMin, data['input'])
        TempMax = max(TempMax, data['input'])
        TempAvg += data['input']

        clr = 'green'
        if data['input'] < 10:
            clr = 'yellow'
            ErrMsg[clr].append(f"Temperature of {data['label']} is low")
        elif data['input'] >= data['crit']:
            clr = 'red'
            ErrMsg[clr].append(f"Temperature of {data['label']} is too high")
        elif data['input'] >= data['max']:
            clr = 'yellow'
            ErrMsg[clr].append(f"Temperature of {data['label']} is high")

        Result += f" <tr> <td>{data['label']}</td> " \
                  f"<td align='right'>{data['input']} &{clr}</td> " \
                  f"<td align='right'>{data['max']}</td> " \
                  "</tr>\n"

    Result += "</table>\n"
    TempAvg /= len(Temp)
    TempAvg = f"{TempAvg:.1f}"

    Result += "<!-- linecount=1 -->\n" \
              f"<!--DEVMON RRD: env 0 0\n" \
              "DS:Temperature:GAUGE:600:-100:100 DS:MinTemp:GAUGE:600:-100:100 DS:MaxTemp:GAUGE:600:-100:100\n" \
              f"temp.cpu {TempAvg}:{TempMin}:{TempMax}\n" \
              "-->"

# ----- MAIN PROGRAM -----
read_sensors()
build_message()
inform_xymon()
