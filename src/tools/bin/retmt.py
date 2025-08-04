#!/usr/bin/env python3
# Migrated from https://wiki.xymonton.org/doku.php/monitors:retmt

import os
import re
import socket
import subprocess
from datetime import datetime

TestName = 'env'  # Test name
ThresholdYellow = 60  # Warning threshold [C]
ThresholdRed = 70  # Error threshold [C]

ColourOf = ['red', 'yellow', 'clear', 'green']

CpuFil = '/sys/class/thermal/thermal_zone0/temp'
GpuCmd = '/usr/bin/vcgencmd measure_temp'


def inform_xymon(ErrMsg):
    XyDisp = os.getenv('XYMSRV')  # Name of monitor server
    XySend = os.getenv('XYMON')  # Monitor interface program
    FmtDate = os.getenv('XYMONDATEFORMAT', '%Y.%m.%d %H:%M:%S')  # Default date format
    if not XyDisp:
        raise EnvironmentError("Environment variable XYMSRV is not set.")
    if not XySend:
        raise EnvironmentError("Environment variable XYMON is not set.")

    colour = 3  # Test status
    ErrMsg_str = ''
    for i, clr in enumerate(ColourOf):
        if ErrMsg[clr]:
            colour = min(colour, i)
            ErrMsg_str = f"{ErrMsg_str}&{clr} " + "\n&".join(ErrMsg[clr]) + "\n"

    if ErrMsg_str:
        ErrMsg_str += "\n"

    hostName = socket.gethostname().replace(".", ",")
    result = (f"status {hostName}.{TestName} {ColourOf[colour]} {datetime.now().strftime(FmtDate)}\n"
              f"<b>Temperature sensor readings</b>\n\n"
              f"{ErrMsg_str}{result}\n")

    subprocess.run([XySend, XyDisp, result], check=True)


def read_sensors():
    Temp = {}  # Temperature readings
    ErrMsg = {colour: [] for colour in ColourOf}  # Error messages

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
        lines = subprocess.check_output(GpuCmd, shell=True, universal_newlines=True).strip().splitlines()
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
    return Temp, ErrMsg


def build_message(Temp, ErrMsg):
    if not Temp:
        return "No data received\n"

    TempMin = 100
    TempAvg = 0
    TempMax = -100

    result = ("<table border=1 cellpadding=5>\n"
             " <tr> <th>Sensor</th> <th>Temp [C]</th> <th>Threshold [C]</th> </tr>\n")

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

        result = (f"{result} <tr> <td>{data['label']}</td> "
                  f"<td align='right'>{data['input']} &{clr}</td> "
                  f"<td align='right'>{data['max']}</td> "
                  "</tr>\n")

    result = f"{result}</table>\n"
    TempAvg /= len(Temp)
    TempAvg = f"{TempAvg:.1f}"

    result = (f"{result}<!-- linecount=1 -->\n"
              f"<!--DEVMON RRD: env 0 0\n"
              "DS:Temperature:GAUGE:600:-100:100 DS:MinTemp:GAUGE:600:-100:100 DS:MaxTemp:GAUGE:600:-100:100\n"
              f"temp.cpu {TempAvg}:{TempMin}:{TempMax}\n"
              "-->")
    return result


def main():
    Temp, ErrMsg = read_sensors()
    result = build_message(Temp, ErrMsg)
    inform_xymon(result, ErrMsg)


if __name__ == "__main__":
    main()
