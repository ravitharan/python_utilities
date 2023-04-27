#! /usr/bin/env python3

import argparse

import sys
import os
import re
from datetime import datetime
import subprocess

TIME_RANGE_PATH = re.compile(r'(\d+:\d+:\d+)\s+(\d+:\d+:\d+)')
TS_FMT = '%H:%M:%S'

def issue_command(command):
    cp = subprocess.run(command,
                        universal_newlines=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE)

    if cp.returncode != 0:
        print(cp.stderr)
        return (False, cp.stderr)
    else: 
        print(cp.stdout)
        return (True, cp.stdout)

def parse_time_stamp_file(t_file):
    line_num = 1
    ts_values = []
    with open (t_file, 'r') as file_in:
        for line in file_in:
            line.strip()
            if line:
                m = TIME_RANGE_PATH.match(line)
                if not m:
                    print(f'line {line_num}: error line is not "h1:m1:s1 h2:m2:s2" format')
                    break
                t_start = m.group(1)
                t_end = m.group(2)
                t_delta = datetime.strptime(t_end, TS_FMT) - datetime.strptime(t_start, TS_FMT)
                ts_values.append([t_start, t_delta.total_seconds()])
    return ts_values


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('input_video', help='Input video stream')
    parser.add_argument('-t', '--tfile', required=True, help='Time stamp file')
    args = parser.parse_args()
    return args

if __name__  == '__main__':
    args = parse_arguments()
    t_file = args.tfile
    in_video = args.input_video

    ts = parse_time_stamp_file(t_file)

    video_concat = 'concat:'

    rm_temp_files = 'rm _temp_.mp4 '

    for i, t_range in enumerate(ts):
        command = f'ffmpeg -y -ss {t_range[0]} -i {in_video} -t {t_range[1]} -acodec aac -vf scale=1280:720 _temp_.mp4'
        print(command)
        issue_command(command.split())

        file_name = f'_temp_video_{i:02}.ts'
        video_ts_file = file_name
        rm_temp_files += file_name + ' '

        command = f'ffmpeg -i _temp_.mp4 -c copy -bsf:v h264_mp4toannexb -f mpegts {video_ts_file}'
        print(command)
        issue_command(command.split())

        if i:
            video_concat += '|'
        video_concat += video_ts_file

    rm_temp_files += '_temp_output.ts'
    command = f'ffmpeg -y -i {video_concat} -c copy _temp_output.ts'
    print(command)
    issue_command(command.split())

    command = f'ffmpeg -y -f mpegts -i _temp_output.ts -c copy -bsf:a aac_adtstoasc output.mp4'
    print(command)
    issue_command(command.split())

    issue_command(rm_temp_files.split())
    print(command)
