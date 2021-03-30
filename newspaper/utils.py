# -*- coding: utf-8 -*-
"""
Holds misc. utility methods which prove to be
useful throughout this library.
"""
__title__ = 'newspaper'
__author__ = 'Lucas Ou-Yang'
__license__ = 'MIT'
__copyright__ = 'Copyright 2014, Lucas Ou-Yang'

import codecs
import hashlib
import logging
import os
import re
import time

from . import settings

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


class FileHelper(object):
    @staticmethod
    def loadResourceFile(filename):
        if not os.path.isabs(filename):
            dirpath = os.path.abspath(os.path.dirname(__file__))
            path = os.path.join(dirpath, 'resources', filename)
        else:
            path = filename
        try:
            f = codecs.open(path, 'r', 'utf-8')
            content = f.read()
            f.close()
            return content
        except IOError:
            raise IOError("Couldn't open file %s" % path)


class ParsingCandidate(object):

    def __init__(self, link_hash):
        self.link_hash = link_hash


class RawHelper(object):
    @staticmethod
    def get_parsing_candidate(raw_html):
        if isinstance(raw_html, str):
            raw_html = raw_html.encode('utf-8', 'replace')
        link_hash = '%s.%s' % (hashlib.md5(raw_html).hexdigest(), time.time())
        return ParsingCandidate(link_hash)


class URLHelper(object):
    @staticmethod
    def get_parsing_candidate(url_to_crawl):
        # Replace shebang in urls
        final_url = url_to_crawl.replace('#!', '?_escaped_fragment_=') \
            if '#!' in url_to_crawl else url_to_crawl
        link_hash = '%s.%s' % (hashlib.md5(final_url).hexdigest(), time.time())
        return ParsingCandidate(link_hash)


class StringSplitter(object):
    def __init__(self, pattern):
        self.pattern = re.compile(pattern)

    def split(self, string):
        if not string:
            return []
        return self.pattern.split(string)


class StringReplacement(object):
    def __init__(self, pattern, replaceWith):
        self.pattern = pattern
        self.replaceWith = replaceWith

    def replaceAll(self, string):
        if not string:
            return ''
        return string.replace(self.pattern, self.replaceWith)


class ReplaceSequence(object):
    def __init__(self):
        self.replacements = []

    def create(self, firstPattern, replaceWith=None):
        result = StringReplacement(firstPattern, replaceWith or '')
        self.replacements.append(result)
        return self

    def append(self, pattern, replaceWith=None):
        return self.create(pattern, replaceWith)

    def replaceAll(self, string):
        if not string:
            return ''

        mutatedString = string
        for rp in self.replacements:
            mutatedString = rp.replaceAll(mutatedString)
        return mutatedString


class TimeoutError(Exception):
    pass





def get_available_languages():
    """Returns a list of available languages and their 2 char input codes
    """
    stopword_files = os.listdir(os.path.join(settings.STOPWORDS_DIR))
    two_dig_codes = [f.split('-')[1].split('.')[0] for f in stopword_files]
    for d in two_dig_codes:
        assert len(d) == 2
    two_dig_codes.sort()
    return two_dig_codes


def extend_config(config, config_items):
    """
    We are handling config value setting like this for a cleaner api.
    Users just need to pass in a named param to this source and we can
    dynamically generate a config object for it.
    """
    for key, val in list(config_items.items()):
        if hasattr(config, key):
            setattr(config, key, val)

    return config
