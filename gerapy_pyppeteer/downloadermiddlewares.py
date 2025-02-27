import asyncio
import math
import random
import sys
import urllib.parse
from io import BytesIO

import pyppeteer
import twisted.internet
from pyppeteer import launch
from pyppeteer.errors import PageError, TimeoutError
from scrapy import signals
from scrapy.http import HtmlResponse
from scrapy.utils.python import global_object_name
from twisted.internet.asyncioreactor import AsyncioSelectorReactor
from twisted.internet.defer import Deferred

from gerapy_pyppeteer.pretend import SCRIPTS as PRETEND_SCRIPTS
from gerapy_pyppeteer.settings import *

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

reactor = AsyncioSelectorReactor(asyncio.get_event_loop())

# install AsyncioSelectorReactor
twisted.internet.reactor = reactor
sys.modules['twisted.internet.reactor'] = reactor


def as_deferred(f):
    """
    transform a Twisted Deffered to an Asyncio Future
    :param f: async function
    """
    return Deferred.fromFuture(asyncio.ensure_future(f))


logger = logging.getLogger('gerapy.pyppeteer')

RESTART_BROWSER_RATE = 20


class PyppeteerMiddleware(object):
    """
    Downloader middleware handling the requests with Puppeteer
    """

    browsers = []
    request_count = 0

    def _retry(self, request, reason, spider):
        """
        get retry request
        :param request:
        :param reason:
        :param spider:
        :return:
        """
        if not self.retry_enabled:
            return

        retries = request.meta.get('retry_times', 0) + 1
        retry_times = self.max_retry_times

        if 'max_retry_times' in request.meta:
            retry_times = request.meta['max_retry_times']

        stats = spider.crawler.stats
        if retries <= retry_times:
            logger.debug("Retrying %(request)s (failed %(retries)d times): %(reason)s",
                         {'request': request, 'retries': retries, 'reason': reason},
                         extra={'spider': spider})
            retryreq = request.copy()
            retryreq.meta['retry_times'] = retries
            retryreq.dont_filter = True
            retryreq.priority = request.priority + self.priority_adjust

            if isinstance(reason, Exception):
                reason = global_object_name(reason.__class__)

            stats.inc_value('retry/count')
            stats.inc_value('retry/reason_count/%s' % reason)
            return retryreq
        else:
            stats.inc_value('retry/max_reached')
            logger.error("Gave up retrying %(request)s (failed %(retries)d times): %(reason)s",
                         {'request': request, 'retries': retries, 'reason': reason},
                         extra={'spider': spider})

    @classmethod
    def from_crawler(cls, crawler):
        """
        init the middleware
        :param crawler:
        :return:
        """
        settings = crawler.settings
        logging_level = settings.get('GERAPY_PYPPETEER_LOGGING_LEVEL', GERAPY_PYPPETEER_LOGGING_LEVEL)
        logging.getLogger('websockets').setLevel(logging_level)
        logging.getLogger('pyppeteer').setLevel(logging_level)

        # init settings
        cls.window_width = settings.get('GERAPY_PYPPETEER_WINDOW_WIDTH', GERAPY_PYPPETEER_WINDOW_WIDTH)
        cls.window_height = settings.get('GERAPY_PYPPETEER_WINDOW_HEIGHT', GERAPY_PYPPETEER_WINDOW_HEIGHT)
        cls.default_user_agent = settings.get('GERAPY_PYPPETEER_DEFAULT_USER_AGENT',
                                              GERAPY_PYPPETEER_DEFAULT_USER_AGENT)
        cls.headless = settings.get('GERAPY_PYPPETEER_HEADLESS', GERAPY_PYPPETEER_HEADLESS)
        cls.dumpio = settings.get('GERAPY_PYPPETEER_DUMPIO', GERAPY_PYPPETEER_DUMPIO)
        cls.ignore_https_errors = settings.get('GERAPY_PYPPETEER_IGNORE_HTTPS_ERRORS',
                                               GERAPY_PYPPETEER_IGNORE_HTTPS_ERRORS)
        cls.slow_mo = settings.get('GERAPY_PYPPETEER_SLOW_MO', GERAPY_PYPPETEER_SLOW_MO)
        cls.ignore_default_args = settings.get('GERAPY_PYPPETEER_IGNORE_DEFAULT_ARGS',
                                               GERAPY_PYPPETEER_IGNORE_DEFAULT_ARGS)
        cls.handle_sigint = settings.get('GERAPY_PYPPETEER_HANDLE_SIGINT', GERAPY_PYPPETEER_HANDLE_SIGINT)
        cls.handle_sigterm = settings.get('GERAPY_PYPPETEER_HANDLE_SIGTERM', GERAPY_PYPPETEER_HANDLE_SIGTERM)
        cls.handle_sighup = settings.get('GERAPY_PYPPETEER_HANDLE_SIGHUP', GERAPY_PYPPETEER_HANDLE_SIGHUP)
        cls.auto_close = settings.get('GERAPY_PYPPETEER_AUTO_CLOSE', GERAPY_PYPPETEER_AUTO_CLOSE)
        cls.devtools = settings.get('GERAPY_PYPPETEER_DEVTOOLS', GERAPY_PYPPETEER_DEVTOOLS)
        cls.executable_path = settings.get('GERAPY_PYPPETEER_EXECUTABLE_PATH', GERAPY_PYPPETEER_EXECUTABLE_PATH)
        cls.disable_extensions = settings.get('GERAPY_PYPPETEER_DISABLE_EXTENSIONS',
                                              GERAPY_PYPPETEER_DISABLE_EXTENSIONS)
        cls.hide_scrollbars = settings.get('GERAPY_PYPPETEER_HIDE_SCROLLBARS', GERAPY_PYPPETEER_HIDE_SCROLLBARS)
        cls.mute_audio = settings.get('GERAPY_PYPPETEER_MUTE_AUDIO', GERAPY_PYPPETEER_MUTE_AUDIO)
        cls.no_sandbox = settings.get('GERAPY_PYPPETEER_NO_SANDBOX', GERAPY_PYPPETEER_NO_SANDBOX)
        cls.disable_setuid_sandbox = settings.get('GERAPY_PYPPETEER_DISABLE_SETUID_SANDBOX',
                                                  GERAPY_PYPPETEER_DISABLE_SETUID_SANDBOX)
        cls.disable_gpu = settings.get('GERAPY_PYPPETEER_DISABLE_GPU', GERAPY_PYPPETEER_DISABLE_GPU)
        cls.single_process = settings.get('GEPAPY_PYPPETEER_SINGLE_PROCESS', GERAPY_PYPPETEER_SINGLE_PROCESS)
        cls.no_zygote = settings.get('GEPAPY_PYPPETEER_NO_ZYGOTE', GEPAPY_PYPPETEER_NO_ZYGOTE)
        cls.download_timeout = settings.get('GERAPY_PYPPETEER_DOWNLOAD_TIMEOUT',
                                            settings.get('DOWNLOAD_TIMEOUT', GERAPY_PYPPETEER_DOWNLOAD_TIMEOUT))
        cls.ignore_resource_types = settings.get('GERAPY_PYPPETEER_IGNORE_RESOURCE_TYPES',
                                                 GERAPY_PYPPETEER_IGNORE_RESOURCE_TYPES)
        cls.screenshot = settings.get('GERAPY_PYPPETEER_SCREENSHOT', GERAPY_PYPPETEER_SCREENSHOT)
        cls.pretend = settings.get('GERAPY_PYPPETEER_PRETEND', GERAPY_PYPPETEER_PRETEND)
        cls.sleep = settings.get('GERAPY_PYPPETEER_SLEEP', GERAPY_PYPPETEER_SLEEP)
        cls.enable_request_interception = settings.getbool('GERAPY_ENABLE_REQUEST_INTERCEPTION',
                                                           GERAPY_ENABLE_REQUEST_INTERCEPTION)
        cls.retry_enabled = settings.getbool('RETRY_ENABLED')
        cls.max_retry_times = settings.getint('RETRY_TIMES')
        cls.retry_http_codes = set(int(x) for x in settings.getlist('RETRY_HTTP_CODES'))
        cls.priority_adjust = settings.getint('RETRY_PRIORITY_ADJUST')

        cls.proxy = settings.get('GEPAPY_PYPPETEER_PROXY', GEPAPY_PYPPETEER_PROXY)
        cls.init_browser_num = settings.get('GEPAPY_PYPPETEER_INIT_BROWSER_NUM', GEPAPY_PYPPETEER_INIT_BROWSER_NUM)

        s = cls()

        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(s.spider_closed, signal=signals.spider_closed)

        return s

    def spider_opened(self, spider):
        spider.logger.info('Spider opened: %s' % spider.name)
        pass

    def spider_closed(self, spider):
        spider.logger.info('Spider closed: %s' % spider.name)
        return as_deferred(self.close_browser())

    async def open_browser(self):
        options = {
            'headless': self.headless,
            'dumpio': self.dumpio,
            'devtools': self.devtools,
            'args': [
                f'--window-size={self.window_width},{self.window_height}',
                f'--disable-dev-shm-usage',
                f'--no-first-run',
            ]
        }
        if self.executable_path:
            options['executablePath'] = self.executable_path
        if self.ignore_https_errors:
            options['ignoreHTTPSErrors'] = self.ignore_https_errors
        if self.slow_mo:
            options['slowMo'] = self.slow_mo
        if self.ignore_default_args:
            options['ignoreDefaultArgs'] = self.ignore_default_args
        if self.handle_sigint:
            options['handleSIGINT'] = self.handle_sigint
        if self.handle_sigterm:
            options['handleSIGTERM'] = self.handle_sigterm
        if self.handle_sighup:
            options['handleSIGHUP'] = self.handle_sighup
        if self.auto_close:
            options['autoClose'] = self.auto_close
        if self.disable_extensions:
            options['args'].append('--disable-extensions')
        if self.hide_scrollbars:
            options['args'].append('--hide-scrollbars')
        if self.mute_audio:
            options['args'].append('--mute-audio')
        if self.no_sandbox:
            options['args'].append('--no-sandbox')
        if self.disable_setuid_sandbox:
            options['args'].append('--disable-setuid-sandbox')
        if self.disable_gpu:
            options['args'].append('--disable-gpu')
        if self.single_process:
            options['args'].append('--single-process')
        if self.no_zygote:
            options['args'].append('--no-zygote')

        # pretend as normal browser
        _pretend = self.pretend  # get global pretend setting
        if _pretend:
            options['ignoreDefaultArgs'] = [
                '--enable-automation'
            ]
            options['args'].append('--disable-blink-features=AutomationControlled')

        # set proxy
        _proxy = self.proxy
        if _proxy:
            options['args'].append(f'--proxy-server={_proxy}')

        logger.debug('Open browser, set options %s', options)

        for i in range(0, self.init_browser_num):
            self.browsers.append(await launch(options))

    async def close_browser(self):
        logging.info("close browser")
        for b in self.browsers:
            await b.close()
        self.browsers.clear()

    async def _process_request(self, request, spider):
        """
        use pyppeteer to process spider
        :param request:
        :param spider:
        :return:
        """

        # close the browser if request count greater than restart rate
        if self.request_count > RESTART_BROWSER_RATE:
            await self.close_browser()
            self.request_count = 0

        # init browser
        if not self.browsers:
            await self.open_browser()

        endpoint = random.choice(self.browsers).wsEndpoint
        browser = await pyppeteer.connect({"browserWSEndpoint": endpoint})
        logging.info("Endpoint is {}".format(endpoint))

        # get pyppeteer meta
        pyppeteer_meta = request.meta.get('pyppeteer') or {}
        logger.debug('pyppeteer_meta %s', pyppeteer_meta)
        if not isinstance(pyppeteer_meta, dict) or len(pyppeteer_meta.keys()) == 0:
            return

        page = await browser.newPage()

        await page.setViewport({'width': self.window_width, 'height': self.window_height})
        self.request_count = self.request_count + 1

        # pre page hook
        if pyppeteer_meta.get('pre_page_hooks'):
            logger.debug('pre page hook')
            try:
                hooks = pyppeteer_meta.get('pre_page_hooks') or []
                assert isinstance(hooks, list)
                for h in hooks:
                    await h(request, page)
            except Exception as e:
                logger.error("pre hook error {}".format(e))
                await page.close()
                return None

        if self.pretend:
            _default_user_agent = self.default_user_agent
            # get Scrapy request ua, exclude default('Scrapy/2.5.0 (+https://scrapy.org)')
            if 'Scrapy' not in request.headers.get('User-Agent').decode():
                _default_user_agent = request.headers.get('User-Agent').decode()
            await page.setUserAgent(_default_user_agent)
            logger.debug('PRETEND_SCRIPTS is run')
            for script in PRETEND_SCRIPTS:
                await page.evaluateOnNewDocument(script)

        # set cookies
        parse_result = urllib.parse.urlsplit(request.url)
        domain = parse_result.hostname
        _cookies = []
        if isinstance(request.cookies, dict):
            _cookies = [{'name': k, 'value': v, 'domain': domain}
                        for k, v in request.cookies.items()]
        for _cookie in _cookies:
            if isinstance(_cookie, dict) and 'domain' not in _cookie.keys():
                _cookie['domain'] = domain
        if isinstance(request.cookies, list):
            _cookies = request.cookies
        if _cookies:
            await page.setCookie(*_cookies)

        # the headers must be set using request interception
        await page.setRequestInterception(self.enable_request_interception)
        if self.enable_request_interception:
            page.on('request', lambda req: asyncio.ensure_future(setup_request_interceptor(req)))
            page.on('response', lambda rsp: asyncio.ensure_future(setup_response_interceptor(rsp)))

            async def setup_request_interceptor(pu_request):
                res_hooks = pyppeteer_meta["request_interceptor_hooks"] or []
                assert isinstance(res_hooks, list)
                for h in res_hooks:
                    await h(page, request, pu_request)

                # handle headers
                overrides = {
                    'headers': pu_request.headers
                }
                # handle resource types
                _ignore_resource_types = self.ignore_resource_types
                if request.meta.get('pyppeteer', {}).get('ignore_resource_types') is not None:
                    _ignore_resource_types = request.meta.get('pyppeteer', {}).get('ignore_resource_types')
                if pu_request.resourceType in _ignore_resource_types:
                    await pu_request.abort()
                else:
                    await pu_request.continue_(overrides)

            async def setup_response_interceptor(pu_response):
                res_hooks = pyppeteer_meta["response_interceptor_hooks"] or []
                assert isinstance(res_hooks, list)
                for h in res_hooks:
                    await h(page, request, pu_response)

        _timeout = self.download_timeout
        if pyppeteer_meta.get('timeout') is not None:
            _timeout = pyppeteer_meta.get('timeout')

        logger.debug('crawling %s', request.url)

        response = None
        try:
            options = {
                'timeout': 1000 * _timeout
            }
            if pyppeteer_meta.get('wait_until'):
                options['waitUntil'] = pyppeteer_meta.get('wait_until')
            logger.debug('request %s with options %s', request.url, options)
            response = await page.goto(
                request.url,
                options=options
            )
        except (PageError, TimeoutError):
            logger.error('error rendering url %s using pyppeteer', request.url)
            await page.close()
            return self._retry(request, 504, spider)

        # wait for dom loaded
        if pyppeteer_meta.get('wait_for'):
            _wait_for = pyppeteer_meta.get('wait_for')
            try:
                logger.debug('waiting for %s', _wait_for)
                if isinstance(_wait_for, dict):
                    await page.waitFor(**_wait_for)
                else:
                    await page.waitFor(_wait_for)
            except TimeoutError:
                logger.error('error waiting for %s of %s', _wait_for, request.url)
                await page.close()
                return self._retry(request, 504, spider)

        # evaluate script
        if pyppeteer_meta.get('script'):
            _script = pyppeteer_meta.get('script')
            logger.debug('evaluating %s', _script)
            await page.evaluate(_script)

        # post page hook
        if pyppeteer_meta.get('post_page_hooks'):
            logger.debug('post page hook')
            try:
                hooks = pyppeteer_meta.get('post_page_hooks')
                assert isinstance(hooks, list)
                for h in hooks:
                    await h(request, page)
            except Exception as e:
                logger.error(e)
                await page.close()
                return self._retry(request, 504, spider)

        # screenshot
        # TODO: maybe add support for `enabled` sub attribute
        _screenshot = self.screenshot
        if pyppeteer_meta.get('screenshot') is not None:
            _screenshot = pyppeteer_meta.get('screenshot')
        screenshot = None
        if _screenshot:
            # pop path to not save img directly in this middleware
            if isinstance(_screenshot, dict) and 'path' in _screenshot.keys():
                _screenshot.pop('path')
            logger.debug('taking screenshot using args %s', _screenshot)
            screenshot = await page.screenshot(_screenshot)
            if isinstance(screenshot, bytes):
                screenshot = BytesIO(screenshot)

        # sleep
        _sleep = self.sleep
        if pyppeteer_meta.get('sleep') is not None:
            _sleep = pyppeteer_meta.get('sleep')
        if _sleep is not None:
            s = random.randrange(math.floor(0.5 * _sleep), math.floor(_sleep * 1.5))
            logger.debug('sleep for %ss', s)
            await asyncio.sleep(s)

        content = await page.content()
        body = str.encode(content)

        # close page and browser
        logger.debug('close pyppeteer')
        await page.close()

        if not response:
            logger.error('get null response by pyppeteer of url %s', request.url)
            return None

        # Necessary to bypass the compression middleware (?)
        response.headers.pop('content-encoding', None)
        response.headers.pop('Content-Encoding', None)

        response = HtmlResponse(
            page.url,
            status=response.status,
            headers=response.headers,
            body=body,
            encoding='utf-8',
            request=request,
        )
        if screenshot:
            response.meta['screenshot'] = screenshot
        return response

    def process_request(self, request, spider):
        """
        process request using pyppeteer
        :param request:
        :param spider:
        :return:
        """
        logger.debug('processing request %s', request)
        return as_deferred(self._process_request(request, spider))
