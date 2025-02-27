import copy

from scrapy import Request


class PyppeteerRequest(Request):
    """
    Scrapy ``Request`` subclass providing additional arguments
    """

    def __init__(self, url, callback=None, wait_until=None, wait_for=None, script=None, proxy=None,
                 sleep=None, timeout=None, ignore_resource_types=None, pretend=None, screenshot=None, meta=None,
                 pre_page_hooks=None, post_page_hooks=None,
                 request_interceptor_hooks=None, response_interceptor_hooks=None,
                 *args, **kwargs):
        """
        :param url: request url
        :param callback: callback
        :param one of "load", "domcontentloaded", "networkidle0", "networkidle2".
                see https://miyakogi.github.io/pyppeteer/reference.html#pyppeteer.page.Page.goto, default is `domcontentloaded`
        :param wait_for: wait for some element to load, also supports dict
        :param script: script to execute
        :param proxy: use proxy for this time, like `http://x.x.x.x:x`
        :param sleep: time to sleep after loaded, override `GERAPY_PYPPETEER_SLEEP`
        :param timeout: load timeout, override `GERAPY_PYPPETEER_DOWNLOAD_TIMEOUT`
        :param ignore_resource_types: ignored resource types, override `GERAPY_PYPPETEER_IGNORE_RESOURCE_TYPES`
        :param pretend: pretend as normal browser, override `GERAPY_PYPPETEER_PRETEND`
        :param screenshot: ignored resource types, see
                https://miyakogi.github.io/pyppeteer/_modules/pyppeteer/page.html#Page.screenshot,
                override `GERAPY_PYPPETEER_SCREENSHOT`
        :param args:
        :param kwargs:
        """
        # use meta info to save args
        meta = copy.deepcopy(meta) or {}
        pyppeteer_meta = meta.get('pyppeteer') or {}

        self.wait_until = pyppeteer_meta.get('wait_until') if pyppeteer_meta.get(
            'wait_until') is not None else (wait_until or 'domcontentloaded')
        self.wait_for = pyppeteer_meta.get('wait_for') if pyppeteer_meta.get('wait_for') is not None else wait_for
        self.script = pyppeteer_meta.get('script') if pyppeteer_meta.get('script') is not None else script
        self.sleep = pyppeteer_meta.get('sleep') if pyppeteer_meta.get('sleep') is not None else sleep
        self.proxy = pyppeteer_meta.get('proxy') if pyppeteer_meta.get('proxy') is not None else proxy
        self.pretend = pyppeteer_meta.get('pretend') if pyppeteer_meta.get('pretend') is not None else pretend
        self.timeout = pyppeteer_meta.get('timeout') if pyppeteer_meta.get('timeout') is not None else timeout
        self.ignore_resource_types = pyppeteer_meta.get('ignore_resource_types') if pyppeteer_meta.get(
            'ignore_resource_types') is not None else ignore_resource_types
        self.screenshot = pyppeteer_meta.get('screenshot') if pyppeteer_meta.get(
            'screenshot') is not None else screenshot
        self.post_page_hooks = pyppeteer_meta.get('post_page_hooks') if pyppeteer_meta.get(
            'post_page_hooks') is not None else post_page_hooks
        self.pre_page_hooks = pyppeteer_meta.get('pre_page_hooks') if pyppeteer_meta.get(
            'pre_page_hooks') is not None else pre_page_hooks
        self.request_interceptor_hooks = pyppeteer_meta.get("request_interceptor_hooks") or request_interceptor_hooks
        self.response_interceptor_hooks = pyppeteer_meta.get("response_interceptor_hooks") or response_interceptor_hooks

        pyppeteer_meta = meta.setdefault('pyppeteer', {})
        pyppeteer_meta['wait_until'] = self.wait_until
        pyppeteer_meta['wait_for'] = self.wait_for
        pyppeteer_meta['script'] = self.script
        pyppeteer_meta['sleep'] = self.sleep
        pyppeteer_meta['proxy'] = self.proxy
        pyppeteer_meta['pretend'] = self.pretend
        pyppeteer_meta['timeout'] = self.timeout
        pyppeteer_meta['screenshot'] = self.screenshot
        pyppeteer_meta['ignore_resource_types'] = self.ignore_resource_types
        pyppeteer_meta['post_page_hooks'] = self.post_page_hooks
        pyppeteer_meta['pre_page_hooks'] = self.pre_page_hooks
        pyppeteer_meta['request_interceptor_hooks'] = self.request_interceptor_hooks
        pyppeteer_meta['response_interceptor_hooks'] = self.response_interceptor_hooks

        super().__init__(url, callback, meta=meta, *args, **kwargs)
