#!pythonrc.py

import os, sys, json, builtins


# to be able to access aio.cross.simulator
import aio
import aio.cross

# placeholder until v1.0
sys.modules["pygbag"] = aio

import time
import inspect
from pathlib import Path
import json


PYCONFIG_PKG_INDEXES_DEV = ["http://localhost:<port>/archives/repo/"]
PYCONFIG_PKG_INDEXES = ["https://krevetco.github.io/pyggame-archives/repo/"]

ENABLE_USER_SITE = False

# the sim does not preload assets and cannot access currentline
# unless using https://github.com/pmp-p/aioprompt/blob/master/aioprompt/__init__.py

if not defined("undefined"):

    class sentinel:
        def __bool__(self):
            return False

        def __repr__(self):
            return "∅"

        def __nonzero__(self):
            return 0

        def __call__(self, *argv, **kw):
            if len(argv) and argv[0] is self:
                return True
            print("Null Pointer Exception")

    define("undefined", sentinel())
    del sentinel

    define("false", False)
    define("true", True)

    # fix const without writing const in that .py because of faulty micropython parser.
    exec("__import__('builtins').const = lambda x:x", globals(), globals())


def overloaded(i, *attrs):
    for attr in attrs:
        if attr in vars(i.__class__):
            if attr in vars(i):
                return True
    return False


builtins.overloaded = overloaded


def DBG(*argv):
    if PyConfig.dev_mode:
        print(*argv)


try:
    # mpy already has execfile
    execfile
except:

    def execfile(filename):
        imports = []

        # this buggy parser is for implementations that do not have ast module.
        # and should not be used with cpython
        with __import__("tokenize").open(str(filename)) as f:
            __prepro = []
            myglobs = ["setup", "loop", "main"]
            tmpl = []

            for l in f.readlines():
                testline = l.split("#")[0].strip(" \r\n,\t")

                if testline.startswith("global ") and (
                    testline.endswith(" setup") or testline.endswith(" loop") or testline.endswith(" main")
                ):
                    tmpl.append([len(__prepro), l.find("g")])
                    __prepro.append("#globals")
                    continue

                elif testline.startswith("import "):
                    testline = testline.replace("import ", "").strip()
                    for elem in map(str.strip, testline.split(",")):
                        elem = elem.split(" as ")[0]
                        if not elem in imports:
                            imports.append(elem)

                elif testline.startswith("from "):
                    testline = testline.replace("from ", "").strip()
                    elem = testline.split(" import ")[0].strip()
                    if not elem in imports:
                        imports.append(elem)

                __prepro.append(l)

                if l[0] in ("""\n\r\t'" """):
                    continue

                if not l.find("=") > 0:
                    continue

                l = l.strip()

                if l.startswith("def "):
                    continue
                if l.startswith("class "):
                    continue

                # maybe found a global assign
                varname = l.split("=", 1)[0].strip(" []()")

                for varname in map(str.strip, varname.split(",")):
                    if varname.find(" ") > 0:
                        continue

                    # it's a comment on an assign !
                    if varname.find("#") >= 0:
                        continue

                    # skip attr assign
                    if varname.find(".") > 0:
                        continue

                    # not a tuple assign
                    if varname.find("(") > 0:
                        continue

                    # not a list assign
                    if varname.find("[") > 0:
                        continue

                    # TODO handle (a,)=(0,) case types

                    if not varname in myglobs:
                        myglobs.append(varname)

            myglob = f"global {', '.join(myglobs)}\n"

            # for helping fixing freshly ported code
            if aio.cross.simulator:
                print(myglob)

            for mark, indent in tmpl:
                __prepro[mark] = " " * indent + myglob

            def dump_code():
                nonlocal __prepro
                print()
                print("_" * 70)
                for i, l in enumerate(__prepro):
                    print(str(i).zfill(5), l, end="")
                print("_" * 70)
                print()

            # if aio.cross.simulator:
            #    dump_code()

            # use of globals() is only valid in __main__ scope
            # we really want the module __main__ dict here
            # whereever from we are called.
            __main__ = __import__("__main__")
            __main__dict = vars(__main__)
            __main__dict["__file__"] = str(filename)
            try:
                code = compile("".join(__prepro), str(filename), "exec")
            except SyntaxError as e:
                # if not aio.cross.simulator:
                dump_code()
                sys.print_exception(e)
                code = None

            if code:
                print(f"180: imports: {imports}")
                exec(code, __main__dict, __main__dict)

        return __import__("__main__")

    define("execfile", execfile)


try:
    PyConfig
    PyConfig["pkg_repolist"] = []

    aio.cross.simulator = False
    sys.argv = PyConfig.pop("argv", [])

except Exception as e:
    sys.print_exception(e)
    # TODO: build a pyconfig extracted from C here
    PyConfig = {}
    PyConfig["dev_mode"] = 1
    PyConfig["run_filename"] = "main.py"
    PyConfig["executable"] = sys.executable
    PyConfig["interactive"] = 1
    print(" - running in wasm simulator - ")
    aio.cross.simulator = True

PyConfig["imports_ready"] = False
PyConfig["pygbag"] = 0


class shell:
    # pending async tasks
    coro = []

    # async top level instance compiler/runner
    runner = None
    is_interactive = None

    if aio.cross.simulator:
        ROOT = os.getcwd()
        HOME = os.getcwd()
    else:
        ROOT = f"/data/data/{sys.argv[0]}"
        HOME = f"/data/data/{sys.argv[0]}/assets"

    ticks = 0
    pgzrunning = None

    @classmethod
    def mktemp(cls, suffix=""):
        cls.ticks += 1
        return f"/tmp/tmp-{cls.ticks}{suffix}"

    @classmethod
    def cat(cls, *argv):
        """dump binary file content"""
        for fn in map(str, argv):
            with open(fn, "rb") as out:
                print(out.read())

    @classmethod
    def more(cls, *argv):
        """dump text file content"""
        for fn in map(str, argv):
            with open(fn, "r") as out:
                print(out.read())

    @classmethod
    def pp(cls, *argv):
        """pretty print objects via json"""
        for obj in argv:
            obj = eval(obj, vars(__import__("__main__")))
            if isinstance(obj, platform.Object_type):
                obj = json.loads(platform.window.JSON.stringify(obj))
            yield json.dumps(obj, sort_keys=True, indent=4)

    @classmethod
    def ls(cls, *argv):
        """list directory content"""
        if not len(argv):
            argv = ["."]
        for arg in map(str, argv):
            for out in sorted(os.listdir(arg)):
                print(out)

    @classmethod
    def reset(cls, *argv, **kw):
        ESC("c")

    @classmethod
    def pg_init(cls):
        import pygame

        if pygame.display.get_init():
            return pygame.display.get_surface()
        screen = pygame.display.set_mode([cls.screen_width, cls.screen_height])
        return screen

    @classmethod
    def find(cls, *argv):
        from pathlib import Path

        if not len(argv):
            argv = [os.getcwd()]
        for root in argv:
            root = Path(root)
            for current, dirnames, filenames in os.walk(root):
                dirname = root.joinpath(Path(current))
                for file in filenames:
                    yield str(dirname / file)

    @classmethod
    def grep(cls, match, *argv):
        for arg in argv:
            if arg.find(match) > 0:
                yield arg

    @classmethod
    def clear(cls, *argv, **kw):
        """clear terminal screen"""
        import pygame

        screen = cls.pg_init()
        screen.fill((0, 0, 0))
        pygame.display.update()

    @classmethod
    def display(cls, *argv, **kw):
        """show images, or last repl pygame surface from _"""
        import pygame

        if not len(argv):
            surf = _
        else:
            arg = argv[-1]
            ext = arg.lower()
            if ext.endswith(".b64"):
                import base64

                ext = arg[:-4]
                with open(arg, "rb") as infile:
                    arg = arg[:-4]
                    with open(arg, "wb") as outfile:
                        base64.decode(infile, outfile)

            if ext.endswith(".six"):
                cls.more(arg)
                return

            if ext.endswith(".bmp"):
                surf = pygame.image.load_basic(arg)
            else:
                surf = pygame.image.load(arg)

        screen = cls.pg_init()
        screen.blit(surf, (1, 1))
        pygame.display.update()

    @classmethod
    def mkdir(cls, *argv):
        exist_ok = "-p" in argv
        for arg in map(str, argv):
            if arg == "-p":
                continue
            os.makedirs(arg, exist_ok=exist_ok)

    @classmethod
    def rx(cls, *argv, **env):
        for arg in map(str, argv):
            if arg.startswith("-"):
                continue
            platform.window.MM.download(arg)
            yield f"file {arg} sent"
        return True

    @classmethod
    async def async_pgzrun(cls, *argv, **env):
        await __import__("pgzero").runner.PGZeroGame(__import__("__main__")).async_run()

    @classmethod
    def pgzrun(cls, *argv, **env):
        import pgzero
        import pgzero.runner

        pgzt = pgzero.runner.PGZeroGame(__import__("__main__")).async_run()
        asyncio.create_task(pgzt)
        return True

    @classmethod
    def wget(cls, *argv, **env):
        import urllib.request

        filename = None
        for arg in map(str, argv):
            if arg.startswith("-O"):
                filename = arg[2:].strip()
                yield f'saving to "{filename}"'
                break

        for arg in map(str, argv):
            if arg.startswith("-O"):
                continue
            fn = filename or str(argv[0]).rsplit("/")[-1]
            try:
                filename, _ = urllib.request.urlretrieve(str(arg), filename=fn)
            except Exception as e:
                yield e

        return True

    @classmethod
    def pwd(cls, *argv):
        print(os.getcwd())

    # only work if pkg name == dist name
    @classmethod
    async def pip(cls, *argv):
        for arg in argv:
            if arg == "install":
                continue
            import aio.toplevel

            # yield f"attempting to install {arg}"
            await PyConfig.importer.async_imports(None, arg)

    @classmethod
    def cd(cls, *argv):
        if len(argv):
            os.chdir(argv[-1])
        else:
            os.chdir(cls.HOME)
        print("[ ", os.getcwd(), " ]")

    @classmethod
    def sha256sum(cls, *argv):
        import hashlib

        for arg in map(str, argv):
            sha256_hash = hashlib.sha256()
            with open(arg, "rb") as f:
                # Read and update hash string value in blocks of 4K
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
                hx = sha256_hash.hexdigest()
                yield f"{hx}  {arg}"

    @classmethod
    def spawn(cls, cmd, *argv, **env):
        # TODO extract env from __main__ snapshot
        if cmd.endswith(".py"):
            if cls.pgzrunning:
                print("a program is already running, using 'stop' cmd before retrying")
                cls.stop()
                cls.pgzrunning = None
                aio.defer(cls.spawn, (cmd, *argv), env, delay=500)

            else:
                execfile(cmd)
            return True
        return False

    @classmethod
    def umask(cls, *argv, **kw):
        yield oct(os.umask(0))
        return True

    @classmethod
    def chmod(cls, *argv, **kw):
        def _current_umask() -> int:
            mask = os.umask(0)
            os.umask(mask)
            return mask

        for arg in argv:
            if arg.startswith("-"):
                continue
            mode = 0o777 & ~_current_umask() | 0o111
            print(f"{mode=}")
            os.chmod(arg, mode)

    @classmethod
    def unzip(cls, *argv, **env):
        import zipfile

        for zip in argv:
            with zipfile.ZipFile(zip, "r") as zip_ref:
                zip_ref.extractall(os.getcwd())

    @classmethod
    def install(cls, *argv, **env):
        import aio.toplevel

        for pkg_file in argv:
            try:
                aio.toplevel.install(pkg_file)
                yield f"{pkg_file} installed"
            except (IOError, zipfile.BadZipFile):
                pdb("397: invalid package", pkg_file)
            except Exception as ex:
                sys.print_exception(ex)

    @classmethod
    def dll(cls, *argv):
        cdll = __import__("ctypes").CDLL(None)
        sym = getattr(cdll, argv[0])
        print("symbol :", sym)
        print(sym(*argv[1:]))
        return True

    @classmethod
    def strace(cls, *argv, **env):
        import aio.trace

        sys.settrace(aio.trace.calls)
        return cls.parse_sync(argv, env)

    @classmethod
    def mute(cls, *argv, **env):
        try:
            pygame.mixer.music.unload()
            yield "music muted"
        except:
            pass

    @classmethod
    def debug(cls, *argv, **env):
        try:
            platform.window.debug()
            yield f"debug mode : on, canvas divider {window.python.config.gui_debug}"
        except:
            pass

    @classmethod
    def help(cls, *objs):
        print(
            """
pygbag shell help
________________________
"""
        )
        if not len(objs):
            objs = [cls]
        for obj in objs:
            for cmd, item in vars(obj).items():
                if isinstance(item, str):
                    continue
                if cmd[0] != "_" and item.__doc__:
                    print(cmd, ":", item.__doc__)
                    print()

    # TODO: use run interactive c-api to run this one.
    @classmethod
    def run(cls, *argv, **env):
        __main__ = __import__("__main__")
        __main__dict = vars(__main__)

        builtins._ = undefined
        cmd = " ".join(argv)

        try:
            time_start = time.time()
            code = compile("builtins._ =" + cmd, "<stdin>", "exec")
            exec(code, __main__dict, __main__dict)
            if builtins._ is undefined:
                return True
            if aio.iscoroutine(_):

                async def run(coro):
                    print(f"async[{cmd}] :", await coro)
                    print(f"time[{cmd}] : {time.time() - time_start:.6f}")

                aio.create_task(run(_), name=cmd)
            else:
                print(builtins._)
                print(f"time[{cmd}] : {time.time() - time_start:.6f}")
                return True
        except SyntaxError as e:
            # try run a file or cmd
            return cls.parse_sync(argv, env)
        return False

    time = run

    @classmethod
    def ps(cls, *argv, **env):
        for t in aio.all_tasks():
            print(t)
        return True

    @classmethod
    def stop(cls, *argv, **env):
        aio.exit = True
        # pgzrun will reset to None next exec
        if not cls.pgzrunning:
            # pgzrun does its own cleanup call
            aio.defer(aio.recycle.cleanup, (), {}, delay=500)
            aio.defer(embed.prompt, (), {}, delay=800)

    @classmethod
    def uptime(cls, *argv, **env):
        import asyncio, platform

        if platform.is_browser:

            def load_display(ft):
                avg = sum(ft) / len(ft)
                try:
                    platform.window.load_avg.innerText = "{:.4f}".format(avg)
                    platform.window.load_min.innerText = "{:.4f}".format(min(ft))
                    platform.window.load_max.innerText = "{:.4f}".format(max(ft))
                    return True
                except:
                    pdb("366:uptime: window.load_* widgets not found")
                    return False

            async def perf_index():
                ft = [0.00001] * 60 * 10
                while not aio.exit:
                    ft.pop(0)
                    ft.append(aio.spent / 0.016666666666666666)
                    if not (aio.ticks % 60):
                        if not load_display(ft):
                            break
                    await asyncio.sleep(0)

            aio.create_task(perf_index())
        else:
            print(f"last frame : {aio.spent / 0.016666666666666666:.4f}")

    # cannot deal with HTML trail properly
    #        @classmethod
    #        async def preload_file(cls, main, callback=None):
    #            # get a relevant list of modules likely to be imported
    #            # and prefetch them if found in repo trees
    #            imports = TopLevel_async_handler.list_imports(code=None, file=main)
    #            print(f"579: missing imports: {list(imports)}")
    #            await TopLevel_async_handler.async_imports(callback, *imports)
    #            PyConfig.imports_ready = True
    #            return True

    @classmethod
    async def preload_code(cls, code, callback=None):
        # get a relevant list of modules likely to be imported
        # and prefetch them if found in repo trees
        #
        #            for want in TopLevel_async_handler.list_imports(code, file=None):
        #                DBG(f"605: preloading import {want=} {callback=}")
        #                await TopLevel_async_handler.async_imports(callback, want)

        await TopLevel_async_handler.async_imports(callback, *TopLevel_async_handler.list_imports(code, file=None))
        PyConfig.imports_ready = True
        return True

    @classmethod
    def interactive(cls, prompt=False):
        if cls.is_interactive:
            return
        # if you don't reach that step
        # your main.py has an infinite sync loop somewhere !
        DBG("642: starting EventTarget in a few seconds")

        print()
        TopLevel_async_handler.instance.banner()

        aio.create_task(platform.EventTarget.process())
        cls.is_interactive = True

        if not shell.pgzrunning:
            del __import__("__main__").__file__
            if prompt:
                cls.runner.prompt()
        else:
            shell.pgzrun()

    @classmethod
    async def runpy(cls, main, *args, **kw):
        code = ""
        shell.pgzrunning = None

        def check_code(file_name):
            nonlocal code
            maybe_sync = False
            has_pygame = False
            with open(file_name, "r") as code_file:
                code = code_file.read()
                code = code.rsplit(TopLevel_async_handler.HTML_MARK, 1)[0]

                # do not check site/final/packed code
                # preload code must be fully async and no pgzero based
                if TopLevel_async_handler.muted:
                    return True

                if code[0:320].find("#!pgzrun") >= 0:
                    shell.pgzrunning = True

                if code.find("asyncio.run") < 0:
                    DBG("622: possibly synchronous code found")
                    maybe_sync = True

                has_pygame = code.find("display.flip(") > 0 or code.find("display.update(") > 0

                if maybe_sync and has_pygame:
                    DBG("628: possibly synchronous+pygame code found")
                    return False
            return True

        if not check_code(main):
            for base in ("pygame", "pg"):
                for func in ("flip", "update"):
                    block = f"{base}.display.{func}()"
                    code = code.replace(block, f"{block};await asyncio.sleep(0)")

        # fix cwd to match a run of main.py from its folder
        realpath = str(main)
        if realpath[0] not in "./":
            realpath = str(Path.cwd() / main)
        __import__("__main__").__file__ = str(realpath)
        cls.HOME = Path(realpath).parent
        os.chdir(cls.HOME)

        await cls.preload_code(code, **kw)

        if TopLevel_async_handler.instance:
            DBG("646: starting shell")
            TopLevel_async_handler.instance.start_console(shell)
        else:
            pdb("651: no async handler loader, starting a default async console")
            shell.debug()
            await TopLevel_async_handler.start_toplevel(platform.shell, console=True)

        if shell.pgzrunning:
            print("600 : pygame zero detected")
            __main__ = __import__("__main__")
            sys._pgzrun = True
            sys.modules["pgzrun"] = type(__main__)("pgzrun")
            import pgzrun

            pgzrun.go = lambda: None
            cb = kw.pop("callback", None)
            await TopLevel_async_handler.async_imports(cb, "pygame.base", "pgzero", "pyfxr", **kw)
            import pgzero
            import pgzero.runner

            pgzero.runner.prepare_mod(__main__)

        TopLevel_async_handler.instance.eval(code)

        if not TopLevel_async_handler.muted:
            print("going interactive")
            DBG("643: TODO detect input/print to select repl debug")
            cls.interactive()

        return code

    @classmethod
    async def source(cls, main, *args, **kw):
        TopLevel_async_handler.muted = True
        try:
            return await cls.runpy(main, *args, **kw)
        finally:
            TopLevel_async_handler.muted = False

    @classmethod
    def parse_sync(shell, line, **env):
        catch = True
        for cmd in line.strip().split(";"):
            cmd = cmd.strip()
            if cmd.find(" ") > 0:
                cmd, args = cmd.split(" ", 1)
                args = args.split(" ")
            else:
                args = ()

            if hasattr(shell, cmd):
                fn = getattr(shell, cmd)

                try:
                    if inspect.isgeneratorfunction(fn):
                        for _ in fn(*args):
                            print(_)
                    elif inspect.iscoroutinefunction(fn):
                        aio.create_task(fn(*args))
                    elif inspect.isasyncgenfunction(fn):
                        print("asyncgen N/I")
                    elif inspect.isawaitable(fn):
                        print("awaitable N/I")
                    else:
                        fn(*args)

                except Exception as cmderror:
                    print(cmderror, file=sys.stderr)
            elif cmd.endswith(".py"):
                shell.coro.append(shell.source(cmd, *args, **env))
            else:
                catch = undefined
        return catch

    @classmethod
    async def exec(cls, sub, **env):
        if inspect.isgenerator(sub):
            for _ in sub:
                print(_)
            return
        elif inspect.isgeneratorfunction(sub):
            for _ in sub(**env):
                print(_)
            return
        elif inspect.iscoroutinefunction(sub):
            await sub(*args)
            return

        from collections.abc import Iterator

        if isinstance(sub, Iterator):
            for _ in sub:
                print(_)
            return
        elif isinstance(
            sub,
            (
                str,
                Path,
            ),
        ):
            # subprocess
            return cls.parse_sync(sub, **env)
        else:
            await sub


PyConfig["shell"] = shell
builtins.shell = shell
# end shell


from types import SimpleNamespace
import builtins

builtins.PyConfig = SimpleNamespace(**PyConfig)
del PyConfig


# make simulations same each time, easier to debug
import random

random.seed(1)

import __EMSCRIPTEN__ as platform

platform.shell = shell


if not aio.cross.simulator:

    def fix_url(maybe_url):
        url = str(maybe_url)
        if url.startswith("http://"):
            pass
        elif url.startswith("https://"):
            pass
        elif url.startswith("https:/"):
            url = "https:/" + url[6:]
        elif url.startswith("http:/"):
            url = "http:/" + url[5:]
        return url

    __EMSCRIPTEN__.fix_url = fix_url

    del fix_url

    def apply_patches():
        # use shell generators instead of subprocesses
        # ==========================================================

        import os

        def popen(iterator, **kw):
            import io

            kw.setdefault("file", io.StringIO(newline="\r\n"))
            for line in iterator:
                print(line, **kw)
            kw["file"].seek(0)
            return kw["file"]

        os.popen = popen

        # add real browser functions
        # ===========================================================

        import webbrowser

        def browser_open(url, new=0, autoraise=True):
            platform.window.open(url, "_blank")

        def browser_open_new(url):
            return browser_open(url, 1)

        def browser_open_new_tab(url):
            return browser_open(url, 2)

        webbrowser.open = browser_open
        webbrowser.open_new = browser_open_new
        webbrowser.open_new_tab = browser_open_new_tab

        # extensions

        def browser_open_file(target=None, accept="*"):
            if target:
                platform.EventTarget.addEventListener("upload", target)
            platform.window.dlg_multifile.click()

        webbrowser.open_file = browser_open_file

        # merge emscripten browser module here ?
        # https://rdb.name/panda3d-webgl.md.html#supplementalmodules/asynchronousloading
        #

        # use bad and deprecated sync XHR for urllib
        # ============================================================

        import urllib
        import urllib.request

        def urlretrieve(maybe_url, filename=None, reporthook=None, data=None):
            url = __EMSCRIPTEN__.fix_url(maybe_url)
            filename = str(filename or f"/tmp/uru-{aio.ticks}")
            rc = platform.window.python.DEPRECATED_wget_sync(str(url), filename)
            if rc == 200:
                return filename, []
            raise Exception(f"urlib.error {rc}")

        urllib.request.urlretrieve = urlretrieve

    if (__WASM__ and __EMSCRIPTEN__) or platform.is_browser:
        port = "443"

        # pygbag mode
        if platform.window.location.href.find("//localhost:") > 0:
            port = str(platform.window.location.port)

            # pygbag developer mode ( --dev )
            if ("-i" in PyConfig.orig_argv) or (port == "8666"):
                PyConfig.dev_mode = 1
                print(sys._emscripten_info)

            PyConfig.pygbag = 1
        else:
            PyConfig.pygbag = 0

        if (PyConfig.dev_mode > 0) or PyConfig.pygbag:
            # in pygbag dev mode use local repo
            PyConfig.pkg_indexes = []
            for idx in PYCONFIG_PKG_INDEXES_DEV:
                redirect = idx.replace("<port>", port)
                PyConfig.pkg_indexes.append(redirect)

            print("807: DEV MODE ON", PyConfig.pkg_indexes)
        else:
            # address cdn
            PyConfig.pkg_indexes = PYCONFIG_PKG_INDEXES

        from platform import window, document, ffi

        class fopen:
            flags = {
                #                'mode': "no-cors",
                "redirect": "follow",
                #                'referrerPolicy': 'no-referrer',
                "credentials": "omit",
            }

            def __init__(self, maybe_url, mode="r", flags=None):
                self.url = __EMSCRIPTEN__.fix_url(maybe_url)
                self.mode = mode
                flags = flags or self.__class__.flags
                print(f'849: fopen: fetching "{self.url}" with {flags=}')
                self.flags = ffi(flags)
                self.tmpfile = None

            async def __aenter__(self):
                import platform

                if "b" in self.mode:
                    self.tmpfile = shell.mktemp()
                    cf = platform.window.cross_file(self.url, self.tmpfile, self.flags)
                    content = await platform.jsiter(cf)
                    self.filelike = open(content, "rb")
                    self.filelike.path = content

                    def rename_to(target):
                        print("rename_to", content, target)
                        # will be closed
                        self.filelike.close()
                        os.rename(self.tmpfile, target)
                        self.tmpfile = None
                        del self.filelike.rename_to
                        return target

                else:
                    import io

                    jsp = platform.window.fetch(self.url, self.flags)
                    response = await platform.jsprom(jsp)
                    content = await platform.jsprom(response.text())
                    if len(content) == 4:
                        print("585 fopen", f"Binary {self.url=} ?")
                    self.filelike = io.StringIO(content)

                    def rename_to(target):
                        with open(target, "wb") as data:
                            date.write(self.filelike.read())
                        del self.filelike.rename_to
                        return target

                self.filelike.rename_to = rename_to
                return self.filelike

            async def __aexit__(self, *exc):
                if self.tmpfile:
                    self.filelike.close()
                    try:
                        os.unlink(self.tmpfile)
                    except FileNotFoundError as e:
                        print("895: async I/O error", e)
                del self.filelike, self.url, self.mode, self.tmpfile
                return False

        platform.fopen = fopen

        async def jsiter(iterator):
            mark = None
            value = undefined
            while mark != undefined:
                value = mark
                await asyncio.sleep(0)
                mark = next(iterator, undefined)
            return value

        platform.jsiter = jsiter

        async def jsprom(prom):
            return await jsiter(platform.window.iterator(prom))

        platform.jsprom = jsprom

        apply_patches()

    del apply_patches

    # convert a emscripten FS path to a blob url
    # TODO: weakmap and GC collect
    def File(path):
        return platform.window.blob(str(path))

    # =================== async import , async console ===================================

    import os

    # set correct umask ( emscripten default is 0 )
    os.umask(0o022)  # already done in aio.toplevel

    import zipfile
    import aio.toplevel
    import ast
    from pathlib import Path

    class TopLevel_async_handler(aio.toplevel.AsyncInteractiveConsole):
        # be re entrant
        import_lock = []

        HTML_MARK = '""" # BEGIN -->'

        repos = []
        mapping = {
            "pygame": "pygame.base",
        }
        may_need = []
        ignore = ["ctypes", "distutils", "installer", "sysconfig"]
        ignore += ["python-dateutil", "matplotlib-pyodide"]
        # ???
        ignore += ["pillow", "fonttools"]

        from pathlib import Path

        repodata = "repodata.json"

        def raw_input(self, prompt=">>> "):
            if len(self.buffer):
                return self.buffer.pop(0)

            # if program wants I/O do not empty buffers
            if self.shell.is_interactive:
                maybe = embed.readline()

                if len(maybe):
                    return maybe
            return None
            # raise EOFError

        def eval(self, source):
            for count, line in enumerate(source.split("\n")):
                if not count:
                    if line.startswith("<"):
                        self.buffer.append(f"#{line}")
                        continue
                self.buffer.append(line)

            if count:
                self.line = None
                self.buffer.insert(0, "#")
            # self.buffer.append("")
            print(f"996: {count} lines queued for async eval")

        @classmethod
        def scan_imports(cls, code, filename, load_try=False):
            required = []
            try:
                root = ast.parse(code, filename)
            except SyntaxError as e:
                print("_" * 40)
                print("1004:", filename)
                print("_" * 40)
                for count, line in enumerate(code.split("\n")):
                    print(str(count).zfill(3), line)
                sys.print_exception(e)
                return required

            for node in ast.walk(root):
                if isinstance(node, ast.Import):
                    module = []
                elif isinstance(node, ast.ImportFrom):
                    module = node.module.split(".")
                else:
                    continue

                for n in node.names:
                    if len(module):
                        mod = module[0] or n.name.split(".")[0]
                    else:
                        mod = n.name.split(".")[0]

                    mod = cls.mapping.get(mod, mod)

                    if mod in cls.ignore:
                        continue

                    if mod in cls.may_need:
                        continue

                    if mod in sys.modules:
                        continue

                    if load_try:
                        try:
                            __import__(mod)
                            continue
                        except (ModuleNotFoundError, ImportError):
                            pass

                    if not mod in required:
                        required.append(mod)

            DBG(f"1020: import scan {filename=} {len(code)=} {required}")
            return required

        @classmethod
        def list_imports(cls, code=None, file=None):
            if code is None:
                if file:
                    with open(file) as fcode:
                        code = fcode.read()
                else:
                    code = ""

            HTML_MARK = '"" # BEGIN -->'

            file = file or "<stdin>"

            for want in cls.scan_imports(code, file):
                # DBG(f"1171: requesting module {want=} for {file=} ")
                repo = None
                for repo in PyConfig.pkg_repolist:
                    if want in cls.may_need:
                        DBG(f"1046: skip module {want=} reason: already requested")
                        break

                    if want in sys.modules:
                        DBG(f"1179: skip module {want=} reason: sys.modules")
                        break

                    if want in repo:
                        cls.may_need.append(want)
                        # DBG(f"1184: module {want=} requested")
                        yield want
                        break
                else:
                    if repo:
                        DBG(f"1063: {repo['-CDN-']=} does not provide {want=}")
                    else:
                        pdb(f"1081: no pkg repository available")

        @classmethod
        def imports(cls, *mods, lvl=0, wants=[]):
            unseen = False
            for mod in mods:
                for dep in cls.repos[0]["packages"].get(mod, {}).get("depends", []):
                    if mod in sys.modules:
                        continue

                    if (not dep in wants) and (not dep in cls.ignore):
                        unseen = True
                        wants.insert(0, dep)

            if lvl < 3 and unseen:
                cls.imports(*wants, lvl=lvl + 1, wants=wants)

            if not lvl:
                for dep in mods:
                    if mod in sys.modules:
                        continue

                    if (not dep in wants) and (not dep in cls.ignore):
                        wants.append(dep)
            # always get numpy first
            if "numpy" in wants:
                wants.remove("numpy")
                wants.insert(0, "numpy")
            # FIXME !
            # FIXME !
            # FIXME !
            # FIXME !
            # FIXME !
            # FIXME !

            if "igraph" in wants:
                if "texttable" in wants:
                    wants.remove("texttable")
                wants.insert(0, "texttable")

            if "pygame_gui" in wants:
                wants.insert(0, "i18n")
            # FIXME !
            # FIXME !
            # FIXME !
            # FIXME !
            # FIXME !
            # FIXME !
            # FIXME !
            # FIXME !
            # FIXME !

            return wants

        # TODO: re order repo on failures
        # TODO: try to download from pypi with
        # https://github.com/brettcannon/mousebender/blob/main/mousebender/simple.py
        # https://peps.python.org/pep-0503/
        # https://wiki.python.org/moin/PyPIJSON

        # TODO: gets deps from pygbag
        # https://github.com/thebjorn/pydeps

        @classmethod
        async def async_get_pkg(cls, want, ex, resume):
            pkg_file = ""
            for repo in PyConfig.pkg_repolist:
                DBG(f"1202: {want=} found : {want in repo}")
                if want in repo:
                    pkg_url = f"{repo['-CDN-']}{repo[want]}"

                    pkg_file = f"/tmp/{repo[want].rsplit('/',1)[-1]}"

                    if pkg_file in aio.toplevel.HISTORY:
                        break

                    cfg = {"io": "url", "type": "fs", "path": pkg_file}
                    print("pkg :", pkg_url)

                    track = platform.window.MM.prepare(pkg_url, json.dumps(cfg))

                    try:
                        await cls.pv(track)
                        zipfile.ZipFile(pkg_file).close()
                        break
                    except (IOError, zipfile.BadZipFile):
                        pdb(f"960: network error on {repo['-CDN-']}, cannot install {pkg_file}")
            else:
                print(f"PKG NOT FOUND : {want=}, {resume=}, {ex=}")
                return None
            return await aio.toplevel.get_repo_pkg(pkg_file, want, resume, ex)

        @classmethod
        def get_pkg(cls, want, ex=None, resume=None):
            return cls.async_get_pkg(want, ex, resume)

        @classmethod
        async def async_imports_init(cls):
            for cdn in PyConfig.pkg_indexes:
                async with platform.fopen(Path(cdn) / cls.repodata) as source:
                    cls.repos.append(json.loads(source.read()))

            # print(json.dumps(cls.repos[0]["packages"], sort_keys=True, indent=4))

            print("referenced packages :", len(cls.repos[0]["packages"]))

            if not len(PyConfig.pkg_repolist):
                await cls.async_repos()

            # print("1117: remapping ?", PyConfig.dev_mode)
            if PyConfig.pygbag > 0:
                for idx, repo in enumerate(PyConfig.pkg_repolist):
                    DBG("1264:", repo["-CDN-"], "REMAPPED TO", PyConfig.pkg_indexes[-1])
                    repo["-CDN-"] = PyConfig.pkg_indexes[-1]

        @classmethod
        async def async_imports(cls, callback, *wanted, **kw):
            def default_cb(pkg, error=None):
                if error:
                    pdb(msg)
                else:
                    DBG(f"\tinstalling {pkg}")

            callback = callback or default_cb

            # init dep solver.
            if not len(cls.repos):
                await cls.async_imports_init()
                del cls.async_imports_init

            all = cls.imports(*wanted)

            # pygame must be early for plotting
            if ("matplotlib" in all) and ("pygame" not in sys.modules):
                await cls.async_get_pkg("pygame.base", None, None)
                __import__("pygame")

            # FIXME: automatically build a deps table for those with buildmap for archive/repo/pkg.
            if "igraph" in all:
                if not "texttable" in sys.modules:
                    callback("texttable")
                    try:
                        await cls.async_get_pkg("texttable", None, None)
                        __import__("texttable")
                    except (IOError, zipfile.BadZipFile):
                        pdb("1310: cannot load texttable")
                if "texttable" in all:
                    all.remove("texttable")

            # FIXME: numpy must be loaded first for some modules.
            # FIXME: THIS IS RE-ENTRANT IN SOME CASES
            if "numpy" in all:
                if not "numpy" in sys.modules:
                    callback("numpy")
                    try:
                        await cls.async_get_pkg("numpy", None, None)
                        __import__("numpy")
                    except (IOError, zipfile.BadZipFile):
                        pdb("1305: cannot load numpy")
                all.remove("numpy")

            for req in all:
                if req == "python-dateutil":
                    req = "dateutil"

                if req == "pillow":
                    req = "PIL"

                if req in cls.ignore or req in sys.modules:
                    print("1291: {req=} in {cls.ignore=} or sys.modules")
                    continue

                callback(req)

                try:
                    await cls.async_get_pkg(req, None, None)
                except (IOError, zipfile.BadZipFile):
                    msg = f"928: cannot download {req} pkg"
                    callback(req, error=msg)
                    continue

        @classmethod
        async def pv(cls, track, prefix="", suffix="", decimals=1, length=70, fill="X", printEnd="\r"):
            # Progress Bar Printing Function
            def print_pg_bar(total, iteration):
                if iteration > total:
                    iteration = total
                percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
                filledLength = int(length * iteration // total)
                bar = fill * filledLength + "-" * (length - filledLength)
                print(f"\r{prefix} |{bar}| {percent}% {suffix}", end=printEnd)

            # Update Progress Bar
            while True:
                if track.pos < 0:
                    raise IOError(404)
                print_pg_bar(track.len or 100, track.pos or 0)
                if track.avail:
                    break
                await asyncio.sleep(0.02)

            # Print New Line on Complete
            print()

        @classmethod
        async def async_repos(cls):
            abitag = f"cp{sys.version_info.major}{sys.version_info.minor}"
            for repo in PyConfig.pkg_indexes:
                async with fopen(f"{repo}index.json", "r") as index:
                    try:
                        data = index.read()
                        if isinstance(data, bytes):
                            data = data.decode()
                        data = data.replace("<abi>", abitag)
                        repo = json.loads(data)
                    except:
                        pdb(f"1394: {repo=}: malformed json index {data}")
                        continue
                    if repo not in PyConfig.pkg_repolist:
                        PyConfig.pkg_repolist.append(repo)

            if PyConfig.dev_mode > 0:
                for idx, repo in enumerate(PyConfig.pkg_repolist):
                    try:
                        print("1353:", repo["-CDN-"], idx, "REMAPPED TO", PyConfig.pkg_indexes[idx])
                        repo["-CDN-"] = PyConfig.pkg_indexes[idx]
                    except Exception as e:
                        sys.print_exception(e)

    # end TopLevel_async_handler


else:
    pdb("TODO: js simulator")


try:
    shell.screen_width = int(platform.window.canvas.width)
    shell.screen_height = int(platform.window.canvas.height)
except:
    shell.screen_width = 1024
    shell.screen_height = 600


# ======================================================
def patch():
    global COLS, LINES, CONSOLE
    import platform

    # DeprecationWarning: Using or importing the ABCs from 'collections'
    # instead of from 'collections.abc' is deprecated since Python 3.3
    # and in 3.10 it will stop working
    import collections
    from collections.abc import MutableMapping

    collections.MutableMapping = MutableMapping

    # could use that ?
    # import _sqlite3
    # sys.modules['sqlite3'] = _sqlite3

    #
    import os

    COLS = platform.window.get_terminal_cols()
    CONSOLE = platform.window.get_terminal_console()
    LINES = platform.window.get_terminal_lines() - CONSOLE

    os.environ["COLS"] = str(COLS)
    os.environ["LINES"] = str(LINES)


    def patch_os_get_terminal_size(fd=0):
        cols = os.environ.get("COLS", 80)
        lines = os.environ.get("LINES", 25)
        try:
            res= (int(cols), int(lines),)
        except:
            res (80, 25,)
        return os.terminal_size(res)

    os.get_terminal_size = patch_os_get_terminal_size

    # fake termios module for some wheel imports
    termios = type(sys)("termios")
    termios.block2 = [
        b"\x03",
        b"\x1c",
        b"\x7f",
        b"\x15",
        b"\x04",
        b"\x00",
        b"\x01",
        b"\x00",
        b"\x11",
        b"\x13",
        b"\x1a",
        b"\x00",
        b"\x12",
        b"\x0f",
        b"\x17",
        b"\x16",
        b"\x00",
        b"\x00",
        b"\x00",
        b"\x00",
        b"\x00",
        b"\x00",
        b"\x00",
        b"\x00",
        b"\x00",
        b"\x00",
        b"\x00",
        b"\x00",
        b"\x00",
        b"\x00",
        b"\x00",
        b"\x00",
    ]

    def patch_termios_getattr(*argv):
        return [17664, 5, 191, 35387, 15, 15, termios.block2]

    def patch_termios_set_raw_mode():
        # assume first set is raw mode
        embed.warn(f"Term phy COLS : {int(platform.window.get_terminal_cols())}")
        embed.warn(f"Term phy LINES : {int(platform.window.get_terminal_lines())}")
        embed.warn(f"Term logical : {patch_os_get_terminal_size()}")
        # set console scrolling zone
        embed.warn(f"Scroll zone start at {LINES=}")
        CSI(f"{LINES+1};{LINES+CONSOLE}r", f"{LINES+2};1H>>> ")
        platform.window.set_raw_mode(1)

    def patch_termios_setattr(*argv):
        if not termios.state:
            patch_termios_set_raw_mode()
        else:
            embed.warn("RESETTING TERMINAL")

        termios.state += 1
        pass

    termios.set_raw_mode = patch_termios_set_raw_mode
    termios.state = 0
    termios.tcgetattr = patch_termios_getattr
    termios.tcsetattr = patch_termios_setattr
    termios.TCSANOW = 0x5402
    termios.TCSAFLUSH = 0x5410
    termios.ECHO = 8
    termios.ICANON = 2
    termios.IEXTEN = 32768
    termios.ISIG = 1
    termios.IXON = 1024
    termios.IXOFF = 4096
    termios.ICRNL = 256
    termios.INLCR = 64
    termios.IGNCR = 128
    termios.VMIN = 6

    sys.modules["termios"] = termios

    # pyodide emulation
    # TODO: implement loadPackage()/pyimport()
    def runPython(code):
        from textwrap import dedent

        print("1285: runPython N/I")

    platform.runPython = runPython

    # fake Decimal module for some wheel imports
    sys.modules["decimal"] = type(sys)("decimal")

    class Decimal:
        pass

    sys.modules["decimal"].Decimal = Decimal

    # patch builtins input()
    async def async_input(prompt=""):
        shell.is_interactive = False
        if prompt:
            print(prompt, end="")
        maybe = ""
        while not len(maybe):
            maybe = embed.readline()
            await asyncio.sleep(0)

        shell.is_interactive = True
        return maybe.rstrip("\n")

    import builtins

    builtins.input = async_input

    #
    def patch_matplotlib_pyplot():
        import matplotlib
        import matplotlib.pyplot

        def patch_matplotlib_pyplot_show(*args, **kwargs):
            import pygame
            import matplotlib.pyplot
            import matplotlib.backends.backend_agg

            figure = matplotlib.pyplot.gcf()
            canvas = matplotlib.backends.backend_agg.FigureCanvasAgg(figure)
            canvas.draw()
            renderer = canvas.get_renderer()
            raw_data = renderer.tostring_rgb()
            size = canvas.get_width_height()

            screen = shell.pg_init()
            surf = pygame.image.fromstring(raw_data, size, "RGB")
            screen.blit(surf, (0, 0))
            pygame.display.update()

        matplotlib.pyplot.show = patch_matplotlib_pyplot_show

        matplotlib.pyplot.__pause__ = matplotlib.pyplot.pause

        def patch_matplotlib_pyplot_pause(interval):
            matplotlib.pyplot.__pause__(0.0001)
            patch_matplotlib_pyplot_show()
            return asyncio.sleep(interval)

        matplotlib.pyplot.pause = patch_matplotlib_pyplot_pause

    #
    def patch_panda3d_showbase():
        import panda3d
        import panda3d.core
        from direct.showbase.ShowBase import ShowBase

        print("panda3d: apply model path patch")
        panda3d.core.get_model_path().append_directory(os.getcwd())

        def run(*argv, **env):
            print("ShowBase.run patched")

        print("panda3d: apply ShowBase.run patch")
        ShowBase.run = run

    def patch_cwcwidth():
        import cwcwidth

        sys.modules["wcwidth"] = cwcwidth

    def patch_pygame():
        import pygame
        import platform_wasm.pygame
        import platform_wasm.pygame.vidcap

        sys.modules["pygame.vidcap"] = platform_wasm.pygame.vidcap

    platform.patches = {
        "matplotlib": patch_matplotlib_pyplot,
        "panda3d": patch_panda3d_showbase,
        "wcwidth": patch_cwcwidth,
        "pygame.base": patch_pygame,
    }


patch()
del patch


# ======================================================
# emulate pyodide display() cmd
# TODO: fixme target
async def display(obj, target=None, **kw):
    filename = shell.mktemp(".png")
    target = kw.pop("target", None)
    x = kw.pop("x", 0)
    y = kw.pop("y", 0)
    dpi = kw.setdefault("dpi", 72)
    if repr(type(obj)).find("matplotlib.figure.Figure") > 0:
        # print(f"matplotlib figure {platform.is_browser=}")
        if platform.is_browser:
            # Agg is not avail, save to svg only option.
            obj.canvas.draw()
            tmp = f"{filename}.svg"
            obj.savefig(tmp, format="svg", **kw)
            await platform.jsiter(platform.window.svg.render(tmp, filename))
        else:
            # desktop matplotlib can save to any format
            obj.canvas.draw()
            obj.savefig(filename, format="png", **kw)

    if target in [None, "pygame"]:
        import pygame

        screen = shell.pg_init()
        screen.fill((0, 0, 0))
        screen.blit(pygame.image.load(filename), (x, y))
        pygame.display.update()


# ======================================================
# x10 mouse and xterm stuff
# https://github.com/muesli/termenv/pull/104
# https://xtermjs.org/docs/api/vtfeatures/
def ESC(*argv):
    for arg in argv:
        sys.__stdout__.write(chr(0x1B))
        sys.__stdout__.write(arg)
    embed.flush()


def CSI(*argv):
    for arg in argv:
        ESC(f"[{arg}")


try:
    console
except:

    class console:
        def log(*argv, **kw):
            import io

            kw["file"] = io.StringIO(newline="\r\n")
            print(*argv, **kw)
            embed.warn(kw["file"].getvalue())


import aio.recycle

# ============================================================
# DO NOT ADD ANYTHING FROM HERE OR APP RECYCLING WILL TRASH IT

#

LOCK = False


async def import_site(__file__, run=True):
    global ENABLE_USER_SITE, LOCK
    if LOCK:
        print("1665: import_site IS NOT RE ENTRANT")
        return

    LOCK = True
    from pathlib import Path

    embed = False
    hint = "main.py"

    try:
        # always start async handler or we could not do imports.
        await TopLevel_async_handler.start_toplevel(platform.shell, console=True)

        if Path(__file__).is_file():
            DBG(f"1601: running {__file__=}")
            TopLevel_async_handler.muted = True
            await shell.source(__file__)
            # allow to set ENABLE_USER_SITE
            await asyncio.sleep(0)
            if ENABLE_USER_SITE:
                DBG(f"1607: {__file__=} done, giving hand to user_site")
                return __file__
            else:
                DBG(f"1690: {__file__=} done : now trying remote sources")
        else:
            DBG(f"1692: {__file__=} NOT FOUND : now trying remote sources")

        # where to retrieve
        import tempfile

        tmpdir = Path(tempfile.gettempdir())

        source = getattr(PyConfig, "frozen", "")
        if source:
            if Path(source).is_file():
                source_path = getattr(PyConfig, "frozen_path", "")
                handler = getattr(PyConfig, "frozen_handler", "")
                DBG("1514: embed path", source_path, "will embed", source, "handled by", handler)
                local = tmpdir / "embed.py"
                with open(source, "r") as src:
                    with open(local, "w") as file:
                        file.write("import sys, pygame;from aio.fetch import FS\n")
                        file.write(src.read())

                        # default handler is run() when embedding
                        if not handler:
                            file.write(
                                """
    __main__ = vars().get('run')
    async def main():
        global __main__
        if 'aio.fetch' in sys.modules:
            import aio.fetch
            await aio.fetch.preload_fetch()
            await asyncio.sleep(0)
        if __main__:
            await __main__()
    asyncio.run(main())
    """
                            )
                        else:
                            async with fopen(handler) as handle:
                                file.write("\n")
                                file.write(handle.read())
                embed = True
            else:
                print(f"1639: invalid embed {source=}")
                return None
            # file has been retrieved stored in local
        else:
            local = None
            # no embed, try sys.argv[0] first, but main.py can only be a hint.
            # of what to run in an archive

            is_py = sys.argv[0].endswith(".py")
            if sys.argv[0] == "main.py" or not is_py:
                source = PyConfig.orig_argv[-1]
                if is_py:
                    hint = sys.argv[0]
            else:
                source = sys.argv[0]
        DBG(f"1745 {local=} {source=} {is_py=} {hint=}")
        if local is None:
            ext = str(source).rsplit(".")[-1].lower()

            if ext == "py":
                local = tmpdir / source.rsplit("/", 1)[-1]
                await shell.exec(shell.wget(f"-O{local}", source))

            # TODO: test tar.bz2 lzma tar.xz
            elif ext in ("zip", "gz", "tar", "apk", "jar"):
                DBG(f"1664: found archive source {source=}")
                # download and unpack into tmpdir
                fname = tmpdir / source.rsplit("/")[-1]

                if ext in ("apk", "jar"):
                    fname = fname + ".zip"

                async with fopen(source, "rb") as zipdata:
                    with open(fname, "wb") as file:
                        file.write(zipdata.read())
                import shutil

                shutil.unpack_archive(fname, tmpdir)
                os.unlink(fname)

                # locate for an entry point after decompression
                hint = "/" + hint.strip("/")
                for file in shell.find(tmpdir):
                    if file.find(hint) > 0:
                        local = tmpdir / file
                        break
                DBG("1725: import_site: found ", local)
            else:
                # maybe base64 or frozen code in html.
                ...

        if local and local.is_file():
            pdir = str(local.parent)
            os.chdir(pdir)
            if "-v" in PyConfig.orig_argv:
                print()
                print("_" * 70)
                with open(local, "r") as source:
                    for i, l in enumerate(source.readlines()):
                        print(str(i).zfill(5), l, end="")
                print()
                print("_" * 70)
                print()

            # TODO: check orig_argv for isolation parameters
            if not pdir in sys.path:
                sys.path.insert(0, pdir)
            if run:
                await shell.runpy(local)
            return str(local)
        else:
            # show why and drop to prompt
            print(f"404: embed={source} or {sys.argv=}")
            shell.interactive(prompt=True)
            return None
    finally:
        LOCK = False
