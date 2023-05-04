from queue import Queue
from concurrent.futures import ThreadPoolExecutor
from collections import deque
from enum import IntEnum
import threading
from typing import Any, Callable, Generator, Union
import logging


class EventType(IntEnum):
    START_SUBTASK = 1
    COMPLETE_SUBTASK = 2
    JOIN_SUBTASK = 3


_EventType = Union[str, EventType]


class Event:

    def __init__(
        self,
        event_type: _EventType,
        *args,
        context=None,
        **kwargs,
    ) -> None:
        self.event_type = event_type
        self.context = context
        self.args = args
        self.kwargs = kwargs
        self.target: Task = None

    @classmethod
    def start_subtask(cls, func, cancel, *args, **kwargs):
        return Event(
            EventType.START_SUBTASK,
            context={
                'func': func,
                'cancel': cancel,
            },
            *args,
            **kwargs,
        )

    @classmethod
    def join_subtask(cls, subtask: 'SubTask'):
        return Event(EventType.JOIN_SUBTASK, context={'subtask': subtask})

    pass


class SubTask:

    def __init__(
        self,
        fn: Callable,
        cancel: Callable[['SubTask'], bool],
        callback: Callable[['SubTask'], Any],
        *args,
        **kwargs,
    ):
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

        self._exception = None
        self._result = None
        self._done = False
        self._cancelled = False
        self._cancel = cancel
        self._lock = threading.Lock()
        self._callback = callback

    def run(self):
        try:
            self._result = self.fn(*self.args, **self.kwargs)
        except Exception as e:
            self._exception = e
        finally:
            self._done = True
            self._callback(self)

    def result(self):
        if self._exception:
            try:
                raise self._exception
            finally:
                # Break a reference cycle with the exception in self._exception
                self = None
        else:
            return self._result

    def cancel(self):
        if not self._cancel or self._done:
            return False
        with self._lock:
            if self._done:
                return
            if self._cancel(self):
                print('取消成功')
                self._cancelled = True
                self._done = True
                return True
            print('取消失败')
        return False

    def cancelled(self):
        return self._cancelled

    def done(self):
        return self._done

    pass


class EventEmitter:
    log = logging.getLogger()

    def __init__(self) -> None:
        self._event_queue = Queue[Event]()
        self._pool = ThreadPoolExecutor()
        self._handler_map = {}

    def emit(self, event: Event):
        self.log.debug(f'emit {event}')
        self._event_queue.put(event)

    def get_handlers(self, event_type: _EventType) -> list['Task']:
        return self._handler_map.get(event_type, [])

    def handle_event(self, event: Event):
        if event.event_type == EventType.START_SUBTASK:
            subtask = SubTask(
                event.context['func'],
                event.context['cancel'],
                lambda x: self.emit(Event(
                    EventType.COMPLETE_SUBTASK,
                    context={'target': event.target},
                )),
                *event.args,
                **event.kwargs,
            )
            f = self._pool.submit(subtask.run)
            if not subtask._cancel:
                subtask._cancel = lambda x: f.cancel()
            return subtask
        elif event.event_type == EventType.JOIN_SUBTASK:
            event.target._waiting_queue.append(event.context['subtask'])
        else:
            raise Exception(f'Unexpected event_type {event.event_type}')
        return None

    def start(self):
        while True:
            event = self._event_queue.get()
            self.log.debug(f'handle {event}')
            if event.event_type == EventType.COMPLETE_SUBTASK:
                task: Task = event.context['target']
                self.run_task(task.next_task, task.run([]))
            else:
                tasks = self.get_handlers(event.event_type)
                for task in tasks:
                    self.run_task(task, event.args)

    def run_task(self, task: 'Task', data: list):
        while task and len(data) > 0:
            data = task.run(data)
            task = task.next_task

    def add_handler(self, event_type: _EventType, task: 'Task'):
        task._emitter = self
        handlers = self._handler_map.get(event_type, [])
        handlers.append(task)
        self._handler_map[event_type] = handlers


class Task:
    log = logging.getLogger()

    def __init__(
        self,
        task: Generator[Union[Any, Event], Any, Any],
        next_task: 'Task',
    ) -> None:
        self._buffer = deque()
        self._task = task
        self._emitter: EventEmitter = None
        self.next_task = next_task
        self._waiting_queue: list[SubTask] = []
        self._subtask_list: list[SubTask] = []
        self._msg = None
        self._exception = None
        self._progress = 0

    def is_blocked(self) -> bool:
        self._subtask_list = [f for f in self._subtask_list if not f.done()]
        self._waiting_queue = [f for f in self._waiting_queue if not f.done()]
        return len(self._waiting_queue) > 0

    def run(self, data: list) -> list:
        self._buffer.extend(data)
        if self._progress == 3:
            return []
        rst = []
        try:
            while True:
                if self.is_blocked():
                    break
                try:
                    if self._progress == 2:
                        try:
                            self._msg = self._buffer.popleft()
                        except IndexError:
                            break
                        self._progress = 1
                    if self._progress == 0:
                        self._progress = 1
                        msg = next(self._task)
                    elif self._progress == 1:
                        msg = self._task.send(self._msg)
                    else:
                        raise Exception(f'Unexpected `_progress` {self._progress}')
                except StopIteration:
                    self._progress = 3
                    for st in self._subtask_list:
                        st.cancel()
                    break
                if isinstance(msg, Event):
                    msg.target = self
                    self._msg = self._emitter.handle_event(msg)
                    if isinstance(self._msg, SubTask):
                        self._subtask_list.append(self._msg)
                else:
                    if msg is None:
                        try:
                            self._msg = self._buffer.popleft()
                        except IndexError:
                            self._progress = 2
                    else:
                        rst.append(msg)
                        self._msg = None
        except Exception as e:
            self._progress = 3
            self.log.debug(f'Task {self} has been terminated, caused by {e.__class__}:{e}')
            self._exception = e
        return rst

    pass
