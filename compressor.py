import argparse
import logging
import logging.handlers
import os
import subprocess

from common import get_size, get_smtp_handler, report


parser = argparse.ArgumentParser(description='Compress the files in the source directory.')
parser.add_argument('working_dir', type=os.path.abspath, help='archiver working directory')
parser.add_argument('--source', default="tar", help='source folder name')
parser.add_argument('--destination', default="xz", help='destination folder name')
parser.add_argument('--temp', default="tmp", help='temporary folder name')
parser.add_argument('-t', '--threads', default="1", help='threads to use for compression')
parser.add_argument('-d', '--debug', action='store_true', help='enable debug logging')


def main():

    # Verify and check inputs
    args = parser.parse_args()
    args.source = str(args.source)
    args.destination = str(args.destination)
    args.temp = str(args.temp)
    args.threads = int(args.threads)

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
        logging.debug(f"compressor starting")

        source_path = os.path.join(args.working_dir, args.source)
        while True:
            archive_list = [x for x in os.listdir(source_path) if x.endswith('tar') or x.endswith('txt')]
            if len(archive_list) == 0:
                break

            for archive in archive_list:
                product = compress(args, os.path.join(source_path, archive))
                report(args.working_dir, f"compressed {os.path.basename(product)} {get_size(product)}")

        logging.debug(f"compressor ending")
    except subprocess.CalledProcessError as e:
        logging.exception('Called Process Error', exc_info=e)
        exit(e.returncode)
    except Exception as e:
        logging.exception('Unhandled Exception', exc_info=e)
        exit(1)


# Function returns True when it has successfully created the next archive file
def compress(args, path):
    logging.debug(f"Starting compress of file {path}")

    # Calculate the resulting filename
    filename = f"{os.path.basename(path)}.xz"
    tmp_path = os.path.join(args.working_dir, args.temp, filename)
    assert not os.path.isfile(tmp_path)
    xz_path = os.path.join(args.working_dir, args.destination, filename)
    assert not os.path.isfile(xz_path)

    # Compress, well, on 4 threads
    command = ['xz', '-z', '-c', f'-T {args.threads}', path]
    try:
        with open(tmp_path, 'w') as f:
            child = subprocess.Popen(command, stdout=f)
            child.wait()

            if child.returncode != 0:
                raise Exception(f"command '{' '.join(command)}' failed with return code {child.returncode}")
    except subprocess.CalledProcessError as e:
        if os.path.isfile(tmp_path):
            os.remove(tmp_path)
        raise e

    # Move the file into the completed folder
    os.rename(tmp_path, xz_path)

    # Delete the uncompressed file
    os.remove(path)
    logging.debug(f"Compression completed {filename}")
    return xz_path


if __name__ == '__main__':
    main()
