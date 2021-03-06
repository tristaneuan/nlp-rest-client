"""
Iterates over files in the text directory, attempts to tar them in batches of a
specified size, optionally uploads them to S3, and cleans up the original files.
"""

import logging
import os
import requests
import shutil
import sys
import tarfile
import traceback
from boto.s3.connection import S3Connection
from boto.s3.key import Key
from optparse import OptionParser
from time import sleep
from utils import chrono_sort, ensure_dir_exists
from uuid import uuid4
#from query_write import TEXT_DIR, TEMP_TEXT_DIR # This causes an optparse error

# Set up logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
fh = logging.FileHandler('query_tar.log')
fh.setLevel(logging.ERROR)
logger.addHandler(fh)
sh = logging.StreamHandler()
sh.setLevel(logging.INFO)
logger.addHandler(sh)

# Allow user to configure options
parser = OptionParser()
parser.add_option('-b', '--batchsize', dest='batchsize', action='store', default=500, help='Specify the maximum number of files in a .tgz batch')
parser.add_option('-l', '--local', dest='local', action='store_true', default=False, help='Specify whether to store text files locally instead of on S3')
(options, args) = parser.parse_args()

BATCHSIZE = options.batchsize
LOCAL = options.local

# Directory variables for query_tar are set here; set vars for query_write there
TEXT_DIR = ensure_dir_exists('/data/text/')
TEMP_TEXT_DIR = ensure_dir_exists('/data/temp_text/')

if not LOCAL:
    bucket = S3Connection().get_bucket('nlp-data')

if __name__ == '__main__':

    # Set to run indefinitely
    while True:

        try:
            bypass_minimum = False
            # Attempt to enforce minimum batch size, continue after 30 seconds if not
            logger.debug('Checking # of files in text directory...')
            num_text_files = len(os.listdir(TEXT_DIR))
            logger.info('There are %i files in the text directory.' % num_text_files)
            if num_text_files == 0:
                logger.info('Waiting 60 seconds for text directory to populate...')
                sleep(60)
                continue
            if num_text_files < BATCHSIZE:
                logger.warning('Current batch does not meet %i file minimum, waiting for 60 seconds...' % BATCHSIZE)
                bypass_minimum = True
                sleep(60)
            logger.info('Sorting text files chronologically.')
            text_files = chrono_sort(TEXT_DIR)

            for n in range(0, len(text_files), BATCHSIZE):
                files_left = len(text_files) - n
                if files_left < BATCHSIZE:
                    if not bypass_minimum:
                        logger.warning('Exhausted chronological file list; refreshing.')
                        break
                # Move text files to temp directory
                text_batch_dir = ensure_dir_exists(os.path.join(TEMP_TEXT_DIR, str(uuid4())))
                for text_file in text_files[n:n+BATCHSIZE]:
                    shutil.move(text_file[0], os.path.join(text_batch_dir, os.path.basename(text_file[0])))
                logger.info('Moving batch to %s; %i files left.' % (text_batch_dir, files_left))

                # Tar batch
                tarball_path = text_batch_dir + '.tgz'
                logger.info('Archiving batch to %s' % tarball_path)
                tarball = tarfile.open(tarball_path, 'w:gz')
                tarball.add(text_batch_dir, '.')
                tarball.close()

                # Get list of wiki ids represented in this batch, remove temp directory
                wids = list(set([docid.split('_')[0] for docid in os.listdir(text_batch_dir)]))
                logger.debug('%s contains wids: %s' % (tarball_path, ','.join(wids)))
                shutil.rmtree(text_batch_dir)

                # Optionally upload to S3
                if not LOCAL:
                    logger.info('Uploading %s to S3' % os.path.basename(tarball_path))
                    k = Key(bucket)
                    k.key = 'text_events/%s' % os.path.basename(tarball_path)
                    k.set_contents_from_filename(tarball_path)
                    os.remove(tarball_path)

                    ## Send post request to start parser for these wiki ids
                    #for wid in wids:
                    #    requests.post('http://nlp-s1:5000/wiki/%s' % wid)
                else:
                    # Record represented wiki ids for future use
                    with open('/data/tarball_key.txt', 'a') as f:
                        f.write('%s\t%s\n' % (tarball_path, ','.join(wids)))
                    logger.debug('Tarball stored locally at %s' % tarball_path)
        except KeyboardInterrupt:
            sys.exit(0)
        except:
            logger.error(traceback.print_exc())
