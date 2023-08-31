from datetime import datetime
from logging import handlers
import os
import random
import string
import subprocess


def convert_tgmk(value):
    if "k" in value:
        value = value.replace('k', '*1e3')
    if "m" in value:
        value = value.replace('m', '*1e6')
    if "g" in value:
        value = value.replace('g', '*1e9')
    if "t" in value:
        value = value.replace('t', '*1e12')
    if "p" in value:
        value = value.replace('p', '*1e15')
    if "K" in value:
        value = value.replace('K', '*2**10')
    if "M" in value:
        value = value.replace('M', '*2**20')
    if "G" in value:
        value = value.replace('G', '*2**30')
    if "T" in value:
        value = value.replace('T', '*2**40')
    if "P" in value:
        value = value.replace('P', '*2**50')

    return int(eval(value))


def get_filename_range_descriptor(first_item, last_item, directory_list):

    # Get the starting range
    index = directory_list.index(first_item)
    if index == 0:
        start_range = first_item[0]
    else:
        start_range = get_shortest_unique_string(first_item, directory_list[index - 1])

    # Now get the ending range, but make sure the ending range is after the start range
    index = directory_list.index(last_item)
    if index == len(directory_list) - 1:
        end_range = last_item[0]
    else:
        end_range = get_shortest_unique_string(last_item, directory_list[index + 1], min_str=start_range)

    # Replace any spaces in these filenames
    start_range = start_range.replace(' ', '_')
    end_range = end_range.replace(' ', '_')

    # Return the completed range descriptor
    return f"{start_range}_to_{end_range}"


def get_shortest_unique_string(include, exclude, min_str=None):
    index = 0
    while True:
        index += 1

        # If either string has no more letters, return the whole included string
        if len(include) == index or len(exclude) == index:
            return include

        # If there is a minimum string we are not higher than, go again
        if min_str is not None and include[0:index] < min_str:
            continue

        # If the strings are no longer the same at this length, return the result
        if include[0:index] != exclude[0:index]:
            return include[0:index]


def get_size(path):
    return int(subprocess.check_output(['du', '-sb', path]).split()[0])


def get_smtp_handler():
    return handlers.SMTPHandler(mailhost=("outbound.electric.net", 25),
                                credentials=('itadministration@generalfusion.com', 'Sp4misbetterinmusubi!'),
                                fromaddr="root@prometheus.local",
                                toaddrs="brian.kelly@generalfusion.com",
                                subject="[Prometheus] Unhandled Exception by Archiver!")


def get_temp_file_name():
    return 'tmp' + ''.join(random.choice(string.ascii_uppercase + string.ascii_lowercase + string.digits)
                           for _ in range(16))


def report(working_dir, line):
    report_path = os.path.join(working_dir, "archiver.log")
    timestamp = datetime.today().strftime('%Y%m%dT%H%M%S')
    with open(report_path, 'a') as f:
        f.write(f"{timestamp} {line}\n")
