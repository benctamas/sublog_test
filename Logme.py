import sublime, sublime_plugin
import datetime

sublime.Region.to_tuple = lambda self: (self.a, self.b)
sublime.View.sel_tuples = lambda self: [ region.to_tuple() for region in self.sel() ]
sublime.View.sel_coords = lambda self: [ (self.rowcol(x[0]), self.rowcol(x[1])) for x in [ region.to_tuple() for region in self.sel() ] ]


class BuffHandler(object):

    def __init__(self, buffer_id, dev_id, filename=None):
        self.buffer_id = buffer_id
        self.dev_id = dev_id
        self.filename = filename
        self.temp_logs = []
        self.named_logs = []
        self.activated = False
        self.size = 0

    @property
    def logs(self):
        return self.named_logs if self.filename else self.tmp_logs
        
    def _apply_temp_log(self):
        if not self.filename:
            print "warning: no filename, can't apply logs"
            return
        while self.temp_logs:
            self._push_log(self.temp_logs.pop(0))
        
    def _push_log(self, data):
        if not self.filename:
            raise Exception("cant push log, no filename")

        data["filename"] = self.filename
        self.logs.append(data)
        self.print_logs()

    def print_logs(self, n=10):
        print u" ".join([ l['event_type'] for l in self.logs[-10:] ])
    
    def log(self, event_type, event_data=None):
        data = {
            "dev_id": self.dev_id, "created_at": datetime.datetime.now(), 
            "event_type": event_type, "event_data": event_data
        }

        self._push_log(data)
    
    def on_filename(self, filename):
        self.filename = filename
        self._apply_temp_log()

    def on_close(self):
        self.log(event_type="closed")

    def on_post_save(self):
        self.log(event_type="saved")

    def on_tool_activated(self):
        self.log(event_type="tool_activated")

    def on_tool_deactivated(self):
        self.log(event_type="tool_deactivated")
        
    def on_activated(self, created, size):
        if self.activated:
            return
        
        self.activated = True
        
        if created:
            self.log(event_type="opened")
        
        self.size = size
        self.log(event_type="activated")
    
    def on_deactivated(self):
        if not self.activated:
            return

        self.activated = False
        self.log(event_type="deactivated")

    def on_modified(self, size):
        if self.size > size:
            self.log(event_type="delete", event_data={'count': self.size - size})
        else:
            self.log(event_type="insert", event_data={'count': size - self.size})
        self.size = size

    def on_cursor_modified(self, rowcolumns):
        self.log(event_type="cursor_changed", event_data=rowcolumns)

    def collapse_logs(self):
        return collapse_buffer_logs(self.logs)


class LogMachine(object):

    def __init__(self, dev_id):
        self.dev_id = dev_id
        self.buffers = {}

    def get_buffer(self, buffer_id, filename):
        created = False
        if buffer_id not in self.buffers:
            created = True
            self.buffers[buffer_id] = BuffHandler(buffer_id=buffer_id, dev_id=self.dev_id, filename=filename)
        buff = self.buffers[buffer_id]
        if filename and not buff.filename:
            buff.set_filename(filename)
        return buff, created


log_machine = LogMachine(dev_id="test")


def is_file_buffer(view):
    if not view.window():
        # no window -> do not is handle as a file buffer
        return False 
    return view.id() in [ v.id() for v in view.window().views() ]


def only_for_file_buffers(f):
    # decorator; do not call wrapped function if view is not a file buffer
    def wrapped(self, view):
        if is_file_buffer(view):
            return f(self, view)
        return 
    return wrapped


class LogListener(sublime_plugin.EventListener):

    def __init__(self, *args, **kwargs):
        super(LogListener, self).__init__(*args, **kwargs)
        self.last_regions = {}
        self.last_activated_tuple = None

    def on_activated(self, view):
        if not is_file_buffer(view):
            if self.last_activated_tuple:
                buff, created = log_machine.get_buffer(*self.last_activated_tuple)
                buff.on_tool_activated()
            return

        buff, created = log_machine.get_buffer(view.buffer_id(), view.file_name())
        buff.on_activated(created, size=view.size())
        self.last_activated_tuple = (view.buffer_id(), view.file_name()) 
        
    def on_deactivated(self, view):
        if not is_file_buffer(view):
            if self.last_activated_tuple:
                buff, created = log_machine.get_buffer(*self.last_activated_tuple)
                buff.on_tool_deactivated()
            return

        buff, created = log_machine.get_buffer(view.buffer_id(), view.file_name())
        buff.on_deactivated()
    
    @only_for_file_buffers
    def on_close(self, view):
        buff, created = log_machine.get_buffer(view.buffer_id(), view.file_name())
        buff.on_close()

    @only_for_file_buffers
    def on_post_save(self, view):
        buff, created = log_machine.get_buffer(view.buffer_id(), view.file_name())
        buff.on_post_save()
 
    @only_for_file_buffers
    def on_modified(self, view):
        buff, created = log_machine.get_buffer(view.buffer_id(), view.file_name())
        buff.on_modified(size=view.size())

    @only_for_file_buffers
    def on_selection_modified(self, view):
        buff, created = log_machine.get_buffer(view.buffer_id(), view.file_name())
        buff.on_cursor_modified(view.sel_coords())
                 
