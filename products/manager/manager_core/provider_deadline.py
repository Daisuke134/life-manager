"""Absolute deadline for the synchronous provider on its single POSIX owner.

A socket read timeout alone restarts on incoming chunks. A scoped real-time
alarm also bounds a blocked iterator. Unsupported/non-main-thread owners and
pre-existing alarms fail closed before any request. No background writer is
left running when the caller stops. Cancellation gets a separate bounded grace.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from hashlib import sha256
import math
import signal
import threading
import time

_active = ContextVar('manager_provider_deadline', default=None)


class _Expired(BaseException):
    """Bypass SDK broad Exception handlers; translated at the host boundary."""


@contextmanager
def _alarm(deadline):
    from .ampersand_api import SessionFailure
    if type(deadline) not in (int,float) or not math.isfinite(deadline):
        raise SessionFailure('finite monotonic deadline required')
    remaining=deadline-time.monotonic()
    if remaining<=0:
        raise SessionFailure('provider deadline elapsed before request')
    if (threading.current_thread() is not threading.main_thread()
            or not hasattr(signal,'setitimer')):
        raise SessionFailure('bounded synchronous provider requires a POSIX main-thread owner')
    if any(signal.getitimer(signal.ITIMER_REAL)):
        raise SessionFailure('provider cannot replace an existing process alarm')
    previous=signal.getsignal(signal.SIGALRM)
    def expire(signum,frame): raise _Expired()
    signal.signal(signal.SIGALRM,expire)
    try:
        signal.setitimer(signal.ITIMER_REAL,remaining)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,previous)


@contextmanager
def provider_deadline(deadline):
    """Bound non-session probes under the same process deadline."""
    from .ampersand_api import SessionFailure
    try:
        with _alarm(deadline):
            yield
    except _Expired:
        raise SessionFailure('provider probe deadline exceeded') from None


def observe_event(event):
    """Retain exact provider identifiers even before an interrupted create ends."""
    state=_active.get()
    if state is None:return
    import re
    for name,prefix,container in (('session_id','sess','session'),('turn_id','turn','turn')):
        value=getattr(event,name,None)
        nested=getattr(event,container,None)
        if value is None:
            value=nested.get('id') if isinstance(nested,dict) else getattr(nested,'id',None)
        if isinstance(value,str) and re.fullmatch(prefix+r'_[A-Za-z0-9_-]{4,128}',value):
            state[name]=value
    if time.monotonic()>=state['deadline']:
        raise _Expired()


def _cancel(state):
    if not state.get('session_id') or state['journal'] is None:
        return 'UNKNOWN_CREATION_OR_TURN'
    from .provider_budget import cancel_and_reconcile
    try:
        with _alarm(time.monotonic()+5):
            # A deadline can interrupt the created-event handler before its
            # durable bind (including during SQLite I/O). Retain observed IDs
            # and repair that binding inside the bounded cancellation grace.
            if state.get('initial_request_id') is not None:
                state['journal'].bind(state['initial_request_id'],state['session_id'])
            if not state.get('turn_id'):
                return 'UNKNOWN_CREATION_OR_TURN'
            receipt=cancel_and_reconcile(state['client'],state['journal'],
                state['session_id'],state['turn_id'],event_key=state['cancel_key'],
                writer_id=state['writer_id'])
        return receipt.status
    except (_Expired,Exception):
        return 'CANCELLATION_UNKNOWN'


def bounded_provider_call(function):
    @wraps(function)
    def call(*args,**kwargs):
        deadline=kwargs.get('deadline_monotonic')
        if deadline is None:return function(*args,**kwargs)
        from .ampersand_api import SessionFailure
        identity=kwargs.get('request_id') or kwargs.get('key') or 'untracked'
        if type(identity) is not str:
            raise ValueError('stable string request identity required')
        suffix=sha256(identity.encode()).hexdigest()[:32]
        state={'client':args[0] if args else kwargs['client'],
               'journal':kwargs.get('journal'),'deadline':deadline,
               'writer_id':kwargs.get('writer_id') or 'initial_'+suffix,
               'cancel_key':'cancel_'+suffix,
               'initial_request_id':kwargs.get('request_id') if function.__name__=='read_initial_turn' else None}
        if function.__name__=='read_followup_turn':
            state['session_id']=args[1] if len(args)>1 else kwargs.get('session_id')
        token=_active.set(state)
        try:
            try:
                with _alarm(deadline):
                    return function(*args,**kwargs)
            except _Expired:
                outcome=_cancel(state)
                raise SessionFailure('provider deadline exceeded; '+outcome) from None
            except SessionFailure:
                # A transport failure may occur before the outer deadline.
                # An exact turn can still be running; cancellation is not success.
                _cancel(state)
                raise
        finally:
            _active.reset(token)
    return call
