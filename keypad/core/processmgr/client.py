
import sys
import subprocess
import pickle
import concurrent.futures
import threading
import queue
import logging
import platform

import os

class RemoteError(RuntimeError): pass
class UnexpectedWorkerTerminationError(RuntimeError): pass

on_windows = platform.system() == 'Windows'

def _make_inheritable(handle):
    if on_windows:
        import msvcrt
        import _winapi
        h = _winapi.DuplicateHandle(
                _winapi.GetCurrentProcess(), msvcrt.get_osfhandle(handle),
                _winapi.GetCurrentProcess(), 0, 1,
                _winapi.DUPLICATE_SAME_ACCESS)
        return h
    else:
        return handle

INTERPRETER_OVERRIDE = None

def _get_interpreter():
    if INTERPRETER_OVERRIDE is not None:
        return INTERPRETER_OVERRIDE
    else:
        return sys.executable

USE_SMOD = True

def _get_worker_args(rh, wh):
    result = [_get_interpreter()]
    if USE_SMOD:
        smod = os.path.join(os.path.dirname(__file__),
                            'bootstrap.py')
        result.append(smod)
    result += [str(int(rh)),
               str(int(wh))]

    return result

class ServerProxy(object):
    def start(self):
        lr, rw = os.pipe()
        rr, lw = os.pipe()

        self.fin = open(lr, 'rb')
        self.fout = open(lw, 'wb')

        child_env = dict(os.environ)
        child_env['PYTHONPATH'] = os.pathsep.join(sys.path)
        kw = {}
        if platform.system() != 'Windows':
            kw['pass_fds'] = rr, rw
        else:
            kw['close_fds'] = False

        rh = _make_inheritable(rr)
        wh = _make_inheritable(rw)


        self.proc = subprocess.Popen(_get_worker_args(rh, wh),
                                     env=child_env,
                                     **kw)
        os.close(rw)
        os.close(rr)

    def send(self, msg):
        try:
            pickle.dump(msg, self.fout)
            self.fout.flush()
            res = pickle.load(self.fin)
        except (Exception) as exc:
            if not self.is_running:
                retcode = self.proc.returncode
                logging.error('Worker process terminated unexpectedly. Return code: %r.', retcode)
                raise UnexpectedWorkerTerminationError('Return code: {}'.format(retcode), retcode) from exc
            else:
                raise

        if res.error is not None:
            raise RemoteError('Failed to execute task on server.') from res.error
        else:
            return res.result

    def interrupt(self):
        import signal
        self.proc.send_signal(signal.SIGINT)

    def kill(self):
        self.proc.kill()

    @property
    def is_running(self):
        return self.proc.poll() is None

    def shutdown(self):
        if self.is_running:
            from .server import ShutdownMessage
            try:
                return self.send(ShutdownMessage())
            finally:
                self.fout.close()
                self.fin.close()

    def restart(self):
        self.shutdown()
        self.start()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.shutdown()
        return False


class _ServerProxyThread:
    def __init__(self):
        self._sp = None
        self._interrupted = False
    def interrupt(self):
        if self._sp is not None:
            self._interrupted = True
            self._sp.interrupt()

    def kill(self):
        if self._sp is not None:
            self._interrupted = True
            self._sp.kill()

    def run(self, q, startup_message=None):
        if startup_message is not None:
            extra_messages = [(True, startup_message, None, None)]
        else:
            extra_messages = []

        error_count = 0
        try:
            with ServerProxy() as sp:
                self._sp = sp

                while True:
                    if extra_messages:
                        m = extra_messages.pop()
                    else:
                        m = q.get()
                    keep_running, task, future, transform = m
                    if not keep_running:
                        return
                    try:
                        if future is None or future.set_running_or_notify_cancel():
                            result = sp.send(task)
                        else:
                            continue
                    except RemoteError as exc:
                        if future is not None:
                            future.set_exception(exc)
                    except UnexpectedWorkerTerminationError as exc:
                        if self._interrupted:
                            return
                        if future is not None:
                            future.set_exception(exc)
                        if error_count >= 4:
                            logging.error('Too many external process crashes. Will not restart.')
                            return
                        else:
                            logging.error('External process crash. Restarting.')
                        error_count += 1
                        sp.restart()
        #                 extra_messages.append((keep_running, task, future, transform))
                        if startup_message is not None:
                            extra_messages.append((True, startup_message, None, None))
                    else:
                        error_count = 0
                        if future is not None:
                            if transform is not None:
                                try:
                                    result = transform(result)
                                except Exception as exc:
                                    future.set_exception(exc)
                                else:
                                    future.set_result(result)
                            else:
                                future.set_result(result)
        finally:
            try:
                while True:
                    _, _, future, _ = q.get_nowait()
                    if future is not None:
                        future.set_exception(UnexpectedWorkerTerminationError())
            except queue.Empty:
                pass
class AsyncServerProxy(object):
    running_instances = set()
    def __init__(self, startup_message=None):
        self.q = queue.Queue()
        self._spthread = _ServerProxyThread()
        self.thread = threading.Thread(target=self._spthread.run, args=(self.q, startup_message))
#         self.thread.daemon = True
    @property
    def is_running(self):
        return self.thread.is_alive()
        
    @classmethod
    def shutdown_all(cls):
        for p in list(cls.running_instances):
            p.shutdown()

    def start(self):
        self.thread.start()
        self.running_instances.add(self)        

    def shutdown(self):
        if self.is_running:
            self.q.put((False, None, None, None))

            def shutdown_thread():
                self.thread.join(timeout=1)
                if self.thread.is_alive():
                    logging.warning('Worker process failed to terminate. Sending SIGINT. Brace yourselves for '
                                    'tracebacks galore!')
                    self._spthread.interrupt()
                    self.thread.join(timeout=1)
                    if self.thread.is_alive():
                        logging.warning('Worker process failed to respond to SIGINT. Sending SIGKILL.')
                        self._spthread.kill()
                        self.thread.join(timeout=1)
                        if self.thread.is_alive():
                            logging.warning('Worker process did not respond to SIGKILL. Leaving it running. '
                                            'I guess the OS has better things to do...')
            th = threading.Thread(target=shutdown_thread)
            th.daemon = True
            th.start()
        try:
            self.running_instances.remove(self)
        except KeyError:
            pass

    def __enter__(self):
        if not self.thread.is_alive():
            self.start()
        return self
        
    def __exit__(self, *args):
        self.shutdown()
        
    def submit(self, task, transform=None):
        future = concurrent.futures.Future()
        self.q.put((True, task, future, transform))
        return future
        
if __name__ == "__main__":
    sp = ServerProxy()

