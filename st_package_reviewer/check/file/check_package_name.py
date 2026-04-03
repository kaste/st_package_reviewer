from . import FileChecker


class CheckPackageName(FileChecker):

    def check(self):
        if not self.package_name:
            return

        if "sublime" not in self.package_name.casefold():
            return

        self.warn(
            "Package name {!r} contains 'sublime'. Avoid using 'sublime' "
            "in package names; it is redundant in this ecosystem and hurts "
            "searchability."
            .format(self.package_name)
        )
