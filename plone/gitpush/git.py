from Products.Five.browser import BrowserView
from zope.publisher.interfaces import IPublishTraverse
from dulwich import web
from dulwich.repo import BaseRepo, MemoryRepo
from zope.interface import implementer, implements
import re
import logging
from ZPublisher.Iterators import IStreamIterator

logger = logging.getLogger('plone.resource.git')

"""
Protocol docs http://git.661346.n2.nabble.com/RFC-PATCH-0-4-Return-of-smart-HTTP-td3792562.html


"""


class ResourceRepo(BaseRepo):
    """Repo that stores refs, objects, and named files in memory.

    MemoryRepos are always bare: they have no working tree and no index, since
    those have a stronger dependency on the filesystem.
    """

    def __init__(self):
        BaseRepo.__init__(self, MemoryObjectStore(), DictRefsContainer({}))
        self._named_files = {}
        self.bare = True

    def _put_named_file(self, path, contents):
        """Write a file to the control dir with the given name and contents.

        :param path: The path to the file, relative to the control dir.
        :param contents: A string to write to the file.
        """
        self._named_files[path] = contents

    def get_named_file(self, path):
        """Get a file from the control dir with a specific name.

        Although the filename should be interpreted as a filename relative to
        the control dir in a disk-baked Repo, the object returned need not be
        pointing to a file in that location.

        :param path: The path to the file, relative to the control dir.
        :return: An open file object, or None if the file does not exist.
        """
        contents = self._named_files.get(path, None)
        if contents is None:
            return None
        return StringIO(contents)

    def open_index(self):
        """Fail to open index for this repo, since it is bare."""
        raise NoIndexPresent()

    @classmethod
    def init_bare(cls, objects, refs):
        """Create a new bare repository in memory.

        :param objects: Objects for the new repository,
            as iterable
        :param refs: Refs as dictionary, mapping names
            to object SHA1s
        """
        ret = cls()
        for obj in objects:
            ret.object_store.add_object(obj)
        for refname, sha in refs.iteritems():
            ret.refs[refname] = sha
        ret._init_files(bare=True)
        return ret


class ResourceBackend(object):
    """A backend for the Git smart server implementation."""
    repo = MemoryRepo()

    def open_repository(self, path):
        """Open the repository at a path.

        :param path: Path to the repository
        :raise NotGitRepository: no git repository was found at path
        :return: Instance of BackendRepo
        """
        return self.repo


class HTTPGitRequest(object):
    """Class encapsulating the state of a single git HTTP request.

    :ivar environ: the WSGI environment for the request.
    """

    def __init__(self, request, dumb=False, handlers=None):
        self.request = request
        self.environ = request
        self.dumb = dumb
        self.handlers = handlers
        self._cache_headers = []
        self._headers = []

    def add_header(self, name, value):
        """Add a header to the response."""
        self._headers.append((name, value))

    def respond(self, status=web.HTTP_OK, content_type=None, headers=None):
        """Begin a response with the given status and other headers."""
        if headers:
            self._headers.extend(headers)
        if content_type:
            self._headers.append(('Content-Type', content_type))
        self._headers.extend(self._cache_headers)

        for header in self._headers:
            self.request.response.setHeader(*header)
        status, reason = status.split(' ', 1)
        status = int(status)
        self.request.response.setStatus(status, reason)
        return self.request.response.write

    def not_found(self, message):
        """Begin a HTTP 404 response and return the text of a message."""
        self._cache_headers = []
        logger.info('Not found: %s', message)
        self.respond(web.HTTP_NOT_FOUND, 'text/plain')
        return message

    def forbidden(self, message):
        """Begin a HTTP 403 response and return the text of a message."""
        self._cache_headers = []
        logger.info('Forbidden: %s', message)
        self.respond(web.HTTP_FORBIDDEN, 'text/plain')
        return message

    def error(self, message):
        """Begin a HTTP 500 response and return the text of a message."""
        self._cache_headers = []
        logger.error('Error: %s', message)
        self.respond(web.HTTP_ERROR, 'text/plain')
        return message

    def nocache(self):
        """Set the response to never be cached by the client."""
        self._cache_headers = [
          ('Expires', 'Fri, 01 Jan 1980 00:00:00 GMT'),
          ('Pragma', 'no-cache'),
          ('Cache-Control', 'no-cache, max-age=0, must-revalidate'),
          ]

    def cache_forever(self):
        """Set the response to be cached forever by the client."""
        now = time.time()
        self._cache_headers = [
          ('Date', date_time_string(now)),
          ('Expires', date_time_string(now + 31536000)),
          ('Cache-Control', 'public, max-age=31536000'),
          ]


def handle_service_request(req, backend, mat):
    service = mat.group().lstrip('/')
    logger.info('Handling service request for %s', service)
    handler_cls = req.handlers.get(service, None)
    if handler_cls is None:
        yield req.forbidden('Unsupported service %s' % service)
        return
    req.nocache()
    write = req.respond(web.HTTP_OK, 'application/x-%s-result' % service)

    input = req.request.BODYFILE
    # This is not necessary if this app is run from a conforming WSGI server.
    # Unfortunately, there's no way to tell that at this point.
    # TODO: git may used HTTP/1.1 chunked encoding instead of specifying
    # content-length
    content_length = req.request.environ.get('CONTENT_LENGTH', '')
    #if content_length:
    #    input = web._LengthLimitedFile(input, int(content_length))
    proto = web.ReceivableProtocol(input.read, write)
    handler = handler_cls(backend, [web.url_prefix(mat)], proto, http_req=req)
    handler.handle()


@implementer(IPublishTraverse)
class GitView(BrowserView):
    """Class encapsulating the state of a git WSGI application.

    :ivar backend: the Backend object backing this application
    """
    subpath = ""

    def publishTraverse(self, request, name):
        # stop traversing, we have arrived
        traverse_subpath = self.request['TraversalRequestNameStack']
        if traverse_subpath:
            traverse_subpath = list(traverse_subpath+[name, ''])
            traverse_subpath.reverse()
            self.subpath = '/'.join(traverse_subpath)
        self.request['TraversalRequestNameStack'] = []
        # return self so the publisher calls this view
        return self

    services = {
      ('GET', re.compile('/HEAD$')): web.get_text_file,
      ('GET', re.compile('/info/refs$')): web.get_info_refs,
      ('GET', re.compile('/objects/info/alternates$')): web.get_text_file,
      ('GET', re.compile('/objects/info/http-alternates$')): web.get_text_file,
      ('GET', re.compile('/objects/info/packs$')): web.get_info_packs,
      ('GET', re.compile('/objects/([0-9a-f]{2})/([0-9a-f]{38})$')): web.get_loose_object,
      ('GET', re.compile('/objects/pack/pack-([0-9a-f]{40})\\.pack$')): web.get_pack_file,
      ('GET', re.compile('/objects/pack/pack-([0-9a-f]{40})\\.idx$')): web.get_idx_file,

      ('POST', re.compile('/git-upload-pack$')): handle_service_request,
      ('POST', re.compile('/git-receive-pack$')): handle_service_request,
    }

    def __init__(self, context, request, dumb=False, handlers=None):
        super(GitView, self).__init__(context, request)
        #self.backend = context
        self.backend = ResourceBackend()
        self.dumb = dumb
        self.handlers = dict(web.DEFAULT_HANDLERS)
        if handlers is not None:
            self.handlers.update(handlers)

    def __call__(self):
        #path = self.request['PATH_INFO']
        path = self.subpath
        method = self.request['REQUEST_METHOD']
        req = HTTPGitRequest(self.request, dumb=self.dumb,
                             handlers=self.handlers)
        # environ['QUERY_STRING'] has qs args
        handler = None
        for smethod, spath in self.services.iterkeys():
            if smethod != method:
                continue
            mat = spath.search(path)
            if mat:
                handler = self.services[smethod, spath]
                break

        if handler is None:
                return req.not_found('Sorry, that method is not supported: %s'%path)

        result = handler(req, self.backend, mat)
        for text in result:
            self.request.response.write(text)

        return self.request.response

    def index(self):
        return self.__call__()

