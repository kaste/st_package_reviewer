import sublime_plugin


class _InternalCommand(sublime_plugin.ApplicationCommand):

    def run(self):
        print("internal")


class FooCommand(sublime_plugin.ApplicationCommand):

    def run(self):
        print("foo")
