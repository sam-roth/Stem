

import weakref
import functools
import traceback
import types
import functools
import logging


import threading


class SignalBase(object): pass


class Intercepter(object):

    def __init__(self):
        self.intercepted = False

    def __call__(self):
        self.intercepted = True

class InstanceSignal(SignalBase):
    def __init__(self, proto_func, chain, sender):
        super().__init__()
        self._observer_methods = weakref.WeakKeyDictionary()
        self._observer_objects = weakref.WeakKeyDictionary()
        self._chain = chain
        self._sender = weakref.ref(sender)
        self._name = proto_func.__name__
        self.errors = []

    def __iadd__(self, observer):
        self.connect(observer)
        return self

    def __isub__(self, observer):
        self.disconnect(observer)
        return self

    def connect(self, observer, add_sender=False):
        if isinstance(observer, types.MethodType):
            try:
                methods = self._observer_methods[observer.__self__]
            except KeyError:
                methods = set()
                self._observer_methods[observer.__self__] = methods

            methods.add((add_sender, observer.__func__))
        else:
            self._observer_objects[observer] = add_sender 

        return observer


    def disconnect(self, observer):
        if isinstance(observer, types.MethodType):
            methods = self._observer_methods[observer.__self__]
            try:
                methods.remove((False, observer.__func__))
            except KeyError:
                methods.remove((True, observer.__func__))
        else:
            del self._observer_objects[observer]


#     @functools.wraps(proto_func)
    def __call__(self, *args, **kw):
        if self._chain is not None:
            self._chain(*args, **kw)

        self.errors = []
        def handle_exception(exc):
            logging.exception("Error in signal handler %r", self._name)
            self.errors.append(exc)

        # use list(...) to strengthen refs prior to iteration
        for observer_self, observer_funcs in list(self._observer_methods.items()):
            for add_sender, observer_func in list(observer_funcs):
                try:
                    if add_sender:
                        observer_func(observer_self, self._sender(), *args, **kw)
                    else:
                        observer_func(observer_self, *args, **kw)
                except Exception as exc:
                    handle_exception(exc)

        for observer, add_sender in list(self._observer_objects.items()):
            try:
                if add_sender:
                    observer(self._sender(), *args, **kw)
                else:
                    observer(*args, **kw)
            except Exception as exc:
                handle_exception(exc)


def makeInstanceSignal(proto_func, chain=None, sender=None):
    return InstanceSignal(proto_func, chain, sender)

class Signal(object):
    def __init__(self, proto_func):
        self._proto_func = proto_func
        self._instances = weakref.WeakKeyDictionary()

    def for_instance(self, instance):
        return self.__get__(instance, None)

    def __get__(self, instance, owner):
        if instance is None:
            self._owner = owner
            return self

        inst = self._instances.get(instance)
        if inst is None:
            method = types.MethodType(self._proto_func,
                                      instance)
            
            inst = makeInstanceSignal(method, sender=instance)

            self._instances[instance] = inst

        return inst


class ClassSignal(object):
    def __init__(self, proto_func):
        self._proto_func = proto_func
        self._instances = weakref.WeakKeyDictionary()


    def __get__(self, instance, owner):
        if owner is None and instance is not None:
            owner = type(instance)

        if owner is not object:
            chain = self.__get__(None, owner.__base__)
        else:
            chain = None

        inst = self._instances.get(owner)
        if inst is None:
            method = types.MethodType(self._proto_func,
                                      owner)
            
            inst = makeInstanceSignal(method, chain, sender=owner)

            self._instances[owner] = inst

        return inst

def handles(signal):
    def result(f):
        signal.connect(f)
        return f
    return result


def main():
    class Test(object):
        @Signal
        def foo(self, bar, baz):
            pass

    class TestMethodHandler(object):

        def on_foo(self, bar, baz):
            print('self={}, bar={}, baz={}'.format(self, bar, baz))
            

    t = Test()
    t2 = Test()

    @handles(t.foo)
    def handler(bar, baz):
        print('bar={}, baz={}'.format(bar, baz))

    h = TestMethodHandler()
    t.foo += h.on_foo

    t.foo(1, 2)
    t.foo(3, 4)

    t2.foo(5, 6)
    t2.foo(7, 8)
    
    t.foo -= handler

    t.foo(5,6)



    
    t.foo -= h.on_foo

    t.foo(7,8)

    t.foo += h.on_foo

    t.foo(9,10)

    del h

    t.foo(11,12)

    

if __name__ == '__main__':
    main()


