import os
import tempfile
import zipfile
import gzip

from concurrent import futures
from io import BytesIO

import boto3

s3 = boto3.client('s3')


def lambda_handler(event, context):
    # Parse and prepare required items from event
    global bucket, path, zipdata
    event = next(iter(event['Records']))
    bucket = event['s3']['bucket']['name']
    key = event['s3']['object']['key']
    path = os.path.dirname(key)
    file_name, extension = os.path.splitext(os.path.basename(key))

    # Zip archive
    if extension == ".zip":
        # Create temporary file
        temp_file = tempfile.mktemp()

        # Fetch and load target file
        s3.download_file(bucket, key, temp_file)
        zipdata = zipfile.ZipFile(temp_file)
        # Call action method with using ThreadPool
        with futures.ThreadPoolExecutor(max_workers=4) as executor:
            future_list = [
                executor.submit(extract, filename)
                for filename in zipdata.namelist()
            ]

        result = {'success': [], 'fail': []}
        for future in future_list:
            filename, status = future.result()
            result[status].append(filename)

    # gz compressed
    if extension == ".gz":
        upload_status = 'success'
        result = {'success': [], 'fail': []}
        new_key = os.path.dirname(key) + '/' + file_name
        try:
            s3.upload_fileobj(
                Fileobj=gzip.GzipFile(
                    None,
                    'rb',
                    fileobj=BytesIO(
                        s3.get_object(Bucket=bucket, Key=key)['Body'].read())),
                Bucket=bucket,
                Key=new_key)
        except Exception as e:
            print(e)
            upload_status = 'fail'
        finally:
            if upload_status == 'fail':
                result['fail'].append(key)
            else:
                result['success'].append(key)

    # Remove extracted archive file
    if len(result['fail']) == 0:
        s3.delete_object(Bucket=bucket, Key=key)

    return result


def extract(filename):
    upload_status = 'success'
    try:
        s3.upload_fileobj(
            BytesIO(zipdata.read(filename)),
            bucket,
            os.path.join(path, filename)
        )
    except Exception:
        upload_status = 'fail'
    finally:
        return filename, upload_status
