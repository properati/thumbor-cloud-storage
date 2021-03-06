#!/usr/bin/python
# -*- coding: utf-8 -*-

# https://github.com/superbalist/thumbor-cloud-storage

# Licensed under the MIT license:
# http://www.opensource.org/licenses/mit-license

import os
import pytz
from datetime import datetime
from gcloud import storage

from thumbor.result_storages import BaseStorage
from thumbor.engines import BaseEngine
from thumbor.utils import logger


# Results Storage
class Storage(BaseStorage):
    PATH_FORMAT_VERSION = 'v2'
    bucket = None

    def __init__(self, context, shared_client=True):
        BaseStorage.__init__(self, context)
        self.shared_client = shared_client
        self.bucket = self._get_bucket()

    def put(self, bytes):
        file_abspath = self._normalize_path(self.context.request.url)
        logger.debug("[RESULT_STORAGE] putting at %s" % file_abspath)
        bucket = self._get_bucket()

        blob = bucket.blob(file_abspath)
        blob.upload_from_string(bytes)

        max_age = self.context.config.MAX_AGE
        blob.cache_control = "public,max-age=%s" % max_age

        if bytes:
            try:
                mime = BaseEngine.get_mimetype(bytes)
                blob.content_type = mime
            except Exception as ex:
                logger.debug("[RESULT_STORAGE] Couldn't determine mimetype: %s" % ex)

        try:
            blob.patch()
        except Exception as ex:
            logger.error("[RESULT_STORAGE] Couldn't patch blob: %s" % ex)

    def get(self):
        path = self.context.request.url
        file_abspath = self._normalize_path(path)
        logger.debug("[RESULT_STORAGE] getting from %s" % file_abspath)

        bucket = self._get_bucket()
        blob = bucket.get_blob(file_abspath)
        if not blob or self._is_expired(blob):
            return None

        try:
            body = blob.download_as_string()
        except Exception as ex:
            logger.error("[RESULT_STORAGE] Couldn't download blob: %s" % ex)
            return None
        else:
            return body

    def last_updated(self):
        path = self.context.request.url
        file_abspath = self._normalize_path(path)
        logger.debug("[RESULT_STORAGE] getting from %s" % file_abspath)

        bucket = self._get_bucket()
        blob = bucket.get_blob(file_abspath)

        if not blob or self._is_expired(blob):
            logger.debug("[RESULT_STORAGE] image not found at %s" % file_abspath)
            return True

        return blob.updated

    @property
    def is_auto_webp(self):
        return self.context.config.AUTO_WEBP and self.context.request.accepts_webp

    def _get_bucket(self):
        parent = self
        if self.shared_client:
            parent = Storage
        if not parent.bucket:
            bucket_id  = self.context.config.get("RESULT_STORAGE_CLOUD_STORAGE_BUCKET_ID")
            project_id = self.context.config.get("RESULT_STORAGE_CLOUD_STORAGE_PROJECT_ID")
            client = storage.Client(project_id)
            parent.bucket = client.get_bucket(bucket_id)
        return parent.bucket

    def _normalize_path(self, path):
        path_segments = [self.context.config.get('RESULT_STORAGE_CLOUD_STORAGE_ROOT_PATH','thumbor/').rstrip('/'), Storage.PATH_FORMAT_VERSION, ]
        if self.is_auto_webp:
            path_segments.append("webp")

        path_segments.extend([self._partition(path), path.lstrip('/'), ])

        normalized_path = os.path.join(*path_segments).replace('http://', '')
        return normalized_path

    def _partition(self, path_raw):
        path = path_raw.lstrip('/')
        return os.path.join("".join(path[0:2]), "".join(path[2:4]))

    def _is_expired(self, blob):
        expire_in_seconds = self.context.config.get('RESULT_STORAGE_EXPIRATION_SECONDS', None)

        if expire_in_seconds is None or expire_in_seconds == 0:
            return False

        timediff = datetime.now(pytz.utc) - blob.updated
        return timediff.seconds > expire_in_seconds
