import json
import logging

from ...lib import jsonc
from . import FileChecker

PLATFORMS = ("Linux", "OSX", "Windows")
PLATFORM_FILENAMES = tuple("Default ({}).sublime-keymap".format(plat)
                           for plat in PLATFORMS)
VALID_FILENAMES = PLATFORM_FILENAMES + ("Default.sublime-keymap",)
BROAD_CONTEXT_KEYS = {"num_selections", "selection_empty"}

l = logging.getLogger(__name__)


class CheckKeymaps(FileChecker):

    def check(self):
        keymap_files = self.glob("**/*.sublime-keymap")

        # ignore unused files
        keymap_files = {path for path in keymap_files
                        if path.name in VALID_FILENAMES}

        if not keymap_files:
            return

        for path in keymap_files:
            k_map = KeyMapping(path)

            with self.file_context(path):
                self._verify_keymap(k_map)
                self._check_broad_bindings(k_map)

    def _verify_keymap(self, k_map):
        allowed_keys = {'keys', 'command', 'args', 'context'}
        required_keys = {'keys', 'command'}

        idx_to_del = set()
        for i, binding in enumerate(k_map.data):
            with self.context("Binding: {}".format(json.dumps(binding, sort_keys=True))):
                keys = set(binding.keys())
                missing_keys = required_keys - keys
                if missing_keys:
                    self.fail("Binding is missing the keys {}".format(missing_keys))

                    # It would be useless to continue analyzing this entry,
                    # so schedule it for deletion
                    idx_to_del.add(i)

                supplementary_keys = keys - allowed_keys
                if supplementary_keys:
                    self.warn("Binding defines supplementary keys {}".format(supplementary_keys))

                if 'keys' in binding:
                    if binding['keys'] == ["<character>"]:
                        if not binding.get('context'):
                            self.fail("'<character>' bindings must have a 'context'")
                            idx_to_del.add(i)
                        continue

                    try:
                        norm_chords = k_map._verify_and_normalize_chords(binding['keys'])
                    except KeyMappingError as e:
                        self.fail(e.args[0])
                        idx_to_del.add(i)
                    else:
                        binding['keys'] = norm_chords

                # TODO verify 'context'

        # do actual deletion (in reverse)
        for i in sorted(idx_to_del, reverse=True):
            del k_map.data[i]

    def _check_broad_bindings(self, k_map):
        for binding in k_map.data:
            if _has_specific_context(binding):
                continue

            self.fail(_broad_binding_message(binding))


def _broad_binding_message(binding):
    context_keys = _context_keys(binding)
    if context_keys:
        intro = "The binding {} only uses broad context keys: {}.".format(
            binding['keys'], ", ".join(context_keys))
    else:
        intro = "The binding {} has no context.".format(binding['keys'])

    return (
        "{} Packages should only ship key bindings that use a specific "
        "context such as 'selector', 'setting.*', or a custom context key. "
        "If the binding defines a main entry-point to your package, move it "
        "to an example keymap instead so users can decide on their own."
        .format(intro)
    )


def _context_keys(binding):
    context = binding.get('context')
    if isinstance(context, dict):
        context = (context,)
    if not context:
        return []

    return [
        clause.get('key') for clause in context
        if isinstance(clause, dict) and isinstance(clause.get('key'), str)
    ]


def _has_specific_context(binding):
    context = binding.get('context')
    if isinstance(context, dict):
        context = (context,)
    if not context:
        return False

    return any(_is_specific_context_clause(clause) for clause in context)


def _is_specific_context_clause(clause):
    if not isinstance(clause, dict):
        return False

    key = clause.get('key')
    return isinstance(key, str) and key not in BROAD_CONTEXT_KEYS


class KeyMappingError(ValueError):
    pass


class KeyMapping:

    def __init__(self, path):
        self.path = path
        self.data = self._load(path)

    @classmethod
    def _load(cls, path):
        with path.open(encoding='utf-8') as f:
            return jsonc.loads(f.read())

    def _verify(self):
        for binding in self.data:
            binding['keys'] = self._verify_and_normalize_chords(binding['keys'])

    @classmethod
    def _verify_and_normalize_chords(cls, chords):
        if not chords or not isinstance(chords, list):
            raise KeyMappingError("'keys' key is empty or not a list")
        norm_chords = []
        for key_chord in chords:
            if len(key_chord) == 1:
                # Any single character key is valid (representing a symbol)
                norm_chords.append(key_chord)
                continue

            elif key_chord in cls.MODIFIERS:
                # Legal since ST4
                if len(chords) == 1:
                    # But we disallow
                    # TODO report minimum version
                    raise KeyMappingError("Single-chord modifier bindings are disallowed")
                norm_chords.append(key_chord)
                continue

            chord_parts = []
            while True:
                key, plus, key_chord = key_chord.partition("+")
                if not key_chord:  # we're at the end
                    if plus:  # a chord with '+' as key
                        key = plus
                    if not cls._key_is_valid(key):
                        raise KeyMappingError("Invalid key '{}'".format(key))
                    chord_parts.sort(key=cls.MODIFIERS.index)
                    chord_parts.append(key)
                    break

                if key == "option":
                    key = "alt"
                elif key == "command":
                    key = "super"
                # TODO "primary"
                if key not in cls.MODIFIERS:
                    raise KeyMappingError("Invalid modifier key '{}'".format(key))

                chord_parts.append(key)

            norm_chords.append("+".join(chord_parts))

        if norm_chords != chords:
            l.debug("normalized chords {!r} to {!r}".format(chords, norm_chords))
        return norm_chords

    @classmethod
    def _key_is_valid(cls, key):
        if len(key) == 1:
            # should include all typable symbols and more
            return not key.isupper()  # not equivalent to `key.islower()`
        elif key in cls._known_keys:
            # multi-character key aliases
            return True
        else:
            return False

    _known_keys = set()
    # _known_keys |= {chr(c) for c in range(ord('a'), ord('z') + 1)}
    _known_keys |= {"f{}".format(i) for i in range(1, 21)}
    _known_keys |= {"keypad{}".format(i) for i in range(10)}
    _known_keys |= {"up", "down", "left", "right",
                    "insert", "delete", "home", "end", "pageup", "pagedown",
                    "backspace", "enter", "tab",
                    "escape", "pause", "break",
                    "space", "context_menu",
                    "keypad_period", "keypad_divide", "keypad_multiply", "keypad_minus",
                    "keypad_plus", "keypad_enter",
                    "browser_back", "browser_forward", "browser_refresh", "browser_stop",
                    "browser_search", "browser_favorites", "browser_home",
                    "clear", "sysreq",
                    # new keys used in the default linux keymaps
                    "open", "close", "save", "undo", "redo", "cut", "copy", "paste", "find",
                    # these have single-character equivalents
                    # TODO resolve these aliases
                    "plus", "minus", "equals", "forward_slash", "backquote",
                    # Note: this list is incomplete and sourced from the default bindings
                    }

    MODIFIERS = ("ctrl", "super", "alt", "altgr", "shift", "primary")
