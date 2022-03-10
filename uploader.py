import argparse
import logging
import logging.handlers
import os
import subprocess
import time

from common import get_size, get_smtp_handler, report

parser = argparse.ArgumentParser(description='Upload files to AWS.')
parser.add_argument('working_dir', type=os.path.abspath, help='archiver working directory')
parser.add_argument('--source', default="gpg", help='source folder name')
parser.add_argument('-d', '--debug', action='store_true', help='enable debug logging')


def main():

    # Verify and check inputs
    args = parser.parse_args()
    args.source = str(args.source)

    # Verify and create any directories we might need
    assert os.path.isdir(args.working_dir)

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.getLogger().addHandler(get_smtp_handler())

    program_start = time.time()

    try:
        logging.debug(f"uploader starting")

        # Get the list of files in the gpg directory
        archive_path = os.path.join(args.working_dir, args.source)
        archive_list = [x for x in os.listdir(archive_path) if x.endswith('gpg')]

        # Transfer the files
        for archive in archive_list:
            path = os.path.join(archive_path, archive)
            size = get_size(path)

            upload(path)
            report(args.working_dir, f"uploaded {archive} {size}")

            # Quit after an hour so we do not transfer during business hours
            if time.time() > program_start + 3000:
                break

        logging.debug(f"uploader ending")
    except subprocess.CalledProcessError as e:
        logging.exception('Called Process Error', exc_info=e)
        exit(e.returncode)
    except Exception as e:
        logging.exception('Unhandled Exception', exc_info=e)
        exit(1)


# Upload the specified file or raise an exception
def upload(path):
    logging.debug(f"Starting encryption of file {path}")

    # Upload the file to aws
    command = ['aws', 's3', 'cp', path, 's3://prometheus-backup-bucket', '--storage-class', 'DEEP_ARCHIVE', '--quiet']
    try:
        child = subprocess.Popen(command)
        child.wait()

        if child.returncode == 1:
            raise Exception(f"command '{' '.join(command)}' failed with return code 1. Is there a network problem?")

        elif child.returncode != 0:
            raise Exception(f"command '{' '.join(command)}' failed with return code {child.returncode}")

    except subprocess.CalledProcessError as e:
        raise e

    # Delete the original file
    os.remove(path)
    logging.debug(f"upload completed {path}")


if __name__ == '__main__':
    main()
