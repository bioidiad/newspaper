# -*- coding: utf-8 -*-
__title__ = 'newspaper'
__author__ = 'Lucas Ou-Yang'
__license__ = 'MIT'
__copyright__ = 'Copyright 2014, Lucas Ou-Yang'

import logging
import copy
import os
import glob
from . import settings

from .cleaners import DocumentCleaner
from .configuration import Configuration
from .extractors import ContentExtractor
from .outputformatters import OutputFormatter
from .utils import (URLHelper, RawHelper, extend_config,
                    get_available_languages)
from .videos.extractors import VideoExtractor

log = logging.getLogger(__name__)


class ArticleException(Exception):
    pass


class Article(object):
    """Article objects abstract an online news article page
    """
    def __init__(self, html, title='', source_url='', config=None, **kwargs):
        """The **kwargs argument may be filled with config values, which
        is added into the config object
        """
        if isinstance(title, Configuration) or \
                isinstance(source_url, Configuration):
            raise ArticleException(
                'Configuration object being passed incorrectly as title or '
                'source_url! Please verify `Article`s __init__() fn.')

        self.config = config or Configuration()
        self.config = extend_config(self.config, kwargs)

        self.extractor = ContentExtractor(self.config)

        self.title = title

        # URL of the "best image" to represent this article
        self.top_img = self.top_image = ''

        # stores image provided by metadata
        self.meta_img = ''

        # All image urls in this article
        self.imgs = self.images = []

        # All videos in this article: youtube, vimeo, etc
        self.movies = []

        # Body text from this article
        self.text = ''

        # `keywords` are extracted via nlp() from the body text
        self.keywords = []

        # `meta_keywords` are extracted via parse() from <meta> tags
        self.meta_keywords = []

        # `tags` are also extracted via parse() from <meta> tags
        self.tags = set()

        # List of authors who have published the article, via parse()
        self.authors = []

        self.publish_date = ''

        # Summary generated from the article's body txt
        self.summary = ''

        # This article's unchanged and raw HTML
        self.html = html

        # The HTML of this article's main node (most important part)
        self.article_html = ''

        # Keep state for downloads and parsing
        self.is_parsed = False

        # Meta description field in the HTML source
        self.meta_description = ""

        # Meta language field in HTML source
        self.meta_lang = ""

        # Meta favicon field in HTML source
        self.meta_favicon = ""

        # Meta site_name field in HTML source
        self.meta_site_name = ""

        # Meta tags contain a lot of structured data, e.g. OpenGraph
        self.meta_data = {}

        # The canonical link of this article if found in the meta data
        self.canonical_link = ""

        # Holds the top element of the DOM that we determine is a candidate
        # for the main body of the article
        self.top_node = None

        # A deepcopied clone of the above object before heavy parsing
        # operations, useful for users to query data in the
        # "most important part of the page"
        self.clean_top_node = None

        # lxml DOM object generated from HTML
        self.doc = None

        # A deepcopied clone of the above object before undergoing heavy
        # cleaning operations, serves as an API if users need to query the DOM
        self.clean_doc = None

        # A property dict for users to store custom data.
        self.additional_data = {}

    def build(self):
        """Build a lone article from a URL independent of the source (newspaper).
        Don't normally call this method b/c it's good to multithread articles
        on a source (newspaper) level.
        """
        self.parse()

    def _parse_scheme_file(self, path):
        try:
            with open(path, "r") as fin:
                return fin.read()
        except OSError as e:
            self.download_exception_msg = e.strerror
            return None

    def parse(self):
        self.doc = self.config.get_parser().fromstring(self.html)
        self.clean_doc = copy.deepcopy(self.doc)

        if self.doc is None:
            # `parse` call failed, return nothing
            return

        # TODO: Fix this, sync in our fix_url() method
        parse_candidate = self.get_parse_candidate()
        self.link_hash = parse_candidate.link_hash  # MD5

        document_cleaner = DocumentCleaner(self.config)
        output_formatter = OutputFormatter(self.config)

        title = self.extractor.get_title(self.clean_doc)
        self.set_title(title)

        authors = self.extractor.get_authors(self.clean_doc)
        self.set_authors(authors)

        meta_lang = self.extractor.get_meta_lang(self.clean_doc)
        self.set_meta_language(meta_lang)

        if self.config.use_meta_language:
            self.extractor.update_language(self.meta_lang)
            output_formatter.update_language(self.meta_lang)

        meta_site_name = self.extractor.get_meta_site_name(self.clean_doc)
        self.set_meta_site_name(meta_site_name)

        meta_description = \
            self.extractor.get_meta_description(self.clean_doc)
        self.set_meta_description(meta_description)

        tags = self.extractor.extract_tags(self.clean_doc)
        self.set_tags(tags)

        meta_keywords = self.extractor.get_meta_keywords(
            self.clean_doc)
        self.set_meta_keywords(meta_keywords)

        meta_data = self.extractor.get_meta_data(self.clean_doc)
        self.set_meta_data(meta_data)

        # Before any computations on the body, clean DOM object
        self.doc = document_cleaner.clean(self.doc)

        self.top_node = self.extractor.calculate_best_node(self.doc)
        if self.top_node is not None:
            video_extractor = VideoExtractor(self.config, self.top_node)
            self.set_movies(video_extractor.get_videos())

            self.top_node = self.extractor.post_cleanup(self.top_node)
            self.clean_top_node = copy.deepcopy(self.top_node)

            text, article_html = output_formatter.get_formatted(
                self.top_node)
            self.set_article_html(article_html)
            self.set_text(text)

        self.is_parsed = True
        self.release_resources()

    def is_valid_body(self):
        """If the article's body text is long enough to meet
        standard article requirements, keep the article
        """
        if not self.is_parsed:
            raise ArticleException('must parse article before checking \
                                    if it\'s body is valid!')
        meta_type = self.extractor.get_meta_type(self.clean_doc)
        wordcount = self.text.split(' ')
        sentcount = self.text.split('.')

        if (meta_type == 'article' and len(wordcount) >
                (self.config.MIN_WORD_COUNT)):
            log.debug('%s verified for article and wc')
            return True

        if self.title is None or len(self.title.split(' ')) < 2:
            log.debug('%s caught for bad title')
            return False

        if len(wordcount) < self.config.MIN_WORD_COUNT:
            log.debug('%s caught for word cnt')
            return False

        if len(sentcount) < self.config.MIN_SENT_COUNT:
            log.debug('%s caught for sent cnt')
            return False

        if self.html is None or self.html == '':
            log.debug('%s caught for no html')
            return False

        log.debug('%s verified for default true')
        return True


    def get_parse_candidate(self):
        """A parse candidate is a wrapper object holding a link hash of this
        article and a final_url of the article
        """
        if self.html:
            return RawHelper.get_parsing_candidate(self.html)
        return URLHelper.get_parsing_candidate(self.html)

    def build_resource_path(self):
        """Must be called after computing HTML/final URL
        """
        res_path = self.get_resource_path()
        if not os.path.exists(res_path):
            os.mkdir(res_path)

    def get_resource_path(self):
        """Every article object has a special directory to store data in from
        initialization to garbage collection
        """
        res_dir_fn = 'article_resources'
        resource_directory = os.path.join(settings.TOP_DIRECTORY, res_dir_fn)
        if not os.path.exists(resource_directory):
            os.mkdir(resource_directory)
        dir_path = os.path.join(resource_directory, '%s_' % self.link_hash)
        return dir_path

    def release_resources(self):
        # TODO: implement in entirety
        path = self.get_resource_path()
        for fname in glob.glob(path):
            try:
                os.remove(fname)
            except OSError:
                pass

    def set_title(self, input_title):
        if input_title:
            self.title = input_title[:self.config.MAX_TITLE]

    def set_text(self, text):
        text = text[:self.config.MAX_TEXT]
        if text:
            self.text = text

    def set_html(self, html):
        """Encode HTML before setting it
        """
        if html:
            if isinstance(html, bytes):
                html = self.config.get_parser().get_unicode_html(html)
            self.html = html

    def set_article_html(self, article_html):
        """Sets the HTML of just the article's `top_node`
        """
        if article_html:
            self.article_html = article_html

    def set_imgs(self, imgs):
        """The motive for this method is the same as above, provide APIs
        for both `article.imgs` and `article.images`
        """
        self.images = imgs
        self.imgs = imgs

    def set_keywords(self, keywords):
        """Keys are stored in list format
        """
        if not isinstance(keywords, list):
            raise Exception("Keyword input must be list!")
        if keywords:
            self.keywords = keywords[:self.config.MAX_KEYWORDS]

    def set_authors(self, authors):
        """Authors are in ["firstName lastName", "firstName lastName"] format
        """
        if not isinstance(authors, list):
            raise Exception("authors input must be list!")
        if authors:
            self.authors = authors[:self.config.MAX_AUTHORS]

    def set_summary(self, summary):
        """Summary here refers to a paragraph of text from the
        title text and body text
        """
        self.summary = summary[:self.config.MAX_SUMMARY]

    def set_meta_language(self, meta_lang):
        """Save langauges in their ISO 2-character form
        """
        if meta_lang and len(meta_lang) >= 2 and \
           meta_lang in get_available_languages():
            self.meta_lang = meta_lang[:2]

    def set_meta_keywords(self, meta_keywords):
        """Store the keys in list form
        """
        self.meta_keywords = [k.strip() for k in meta_keywords.split(',')]

    def set_meta_favicon(self, meta_favicon):
        self.meta_favicon = meta_favicon

    def set_meta_site_name(self, meta_site_name):
        self.meta_site_name = meta_site_name

    def set_meta_description(self, meta_description):
        self.meta_description = meta_description

    def set_meta_data(self, meta_data):
        self.meta_data = meta_data

    def set_tags(self, tags):
        self.tags = tags

    def set_movies(self, movie_objects):
        """Trim video objects into just urls
        """
        movie_urls = [o.src for o in movie_objects if o and o.src]
        self.movies = movie_urls

    def throw_if_not_parsed_verbose(self):
        """Parse `is_parsed` status -> log readable status
        -> maybe throw ArticleException
        """
        if not self.is_parsed:
            raise ArticleException('You must `parse()` an article first!')
