import argparse
import logging
import logging.handlers
import os
import subprocess

from common import get_size, get_smtp_handler, report

parser = argparse.ArgumentParser(description='Encrypt the files in xz folder in the destination.')
parser.add_argument('working_dir', type=os.path.abspath, help='archiver working directory')
parser.add_argument('--source', default="xz", help='source folder name')
parser.add_argument('--destination', default="gpg", help='destination folder name')
parser.add_argument('--temp', default="tmp", help='temporary folder name')
parser.add_argument('-d', '--debug', action='store_true', help='enable debug logging')


def main():

    # Verify and check inputs
    args = parser.parse_args()
    args.source = str(args.source)
    args.destination = str(args.destination)
    args.temp = str(args.temp)

    # Verify and create any directories we might need
    assert os.path.isdir(args.working_dir)
    path = os.path.join(args.working_dir, args.destination)
    if not os.path.exists(path):
        os.makedirs(path)

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.getLogger().addHandler(get_smtp_handler())

    try:
        logging.debug(f"encrypter starting")

        archive_path = os.path.join(args.working_dir, args.source)
        while True:
            archive_list = [x for x in os.listdir(archive_path) if x.endswith('xz')]
            if len(archive_list) == 0:
                break

            for archive in archive_list:
                product = encrypt(args, os.path.join(archive_path, archive))
                report(args.working_dir, f"encrypted {os.path.basename(product)} {get_size(product)}")

        logging.debug(f"encrypter ending")
    except subprocess.CalledProcessError as e:
        logging.exception('Called Process Error', exc_info=e)
        exit(e.returncode)
    except Exception as e:
        logging.exception('Unhandled Exception', exc_info=e)
        exit(1)


# Function encrypts the passed file returning the new name or raises an exception
def encrypt(args, path):
    logging.debug(f"Starting encryption of file {path}")

    # Calculate the resulting filename
    filename = f"{os.path.basename(path)}.gpg"
    tmp_path = os.path.join(args.working_dir, args.temp, filename)
    assert not os.path.isfile(tmp_path)
    gpg_path = os.path.join(args.working_dir, args.destination, filename)
    assert not os.path.isfile(gpg_path)

    # Specify the command to encrypt
    command = ['gpg', '-c', '--cipher-algo', 'AES256', '--batch',
               '--passphrase-file', os.path.join(args.working_dir, 'passphrase.txt'),
               '--output', tmp_path, path]
    try:
        child = subprocess.Popen(command)
        child.wait()

        if child.returncode != 0:
            raise Exception(f"command '{' '.join(command)}' failed with return code {child.returncode}")
    except subprocess.CalledProcessError as e:
        if os.path.isfile(tmp_path):
            os.remove(tmp_path)
        raise e

    # Move the file into the completed folder
    os.rename(tmp_path, gpg_path)

    # Delete the uncompressed file
    os.remove(path)
    logging.debug(f"encryption completed {filename}")
    return gpg_path


if __name__ == '__main__':
    main()
