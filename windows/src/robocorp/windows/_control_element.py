import inspect
import itertools
import logging
import re
import sys
import typing
from pathlib import Path
from typing import Callable, Iterator, List, Literal, Optional, Protocol, Tuple, Union

from _ctypes import COMError

from robocorp.windows._errors import ActionNotPossible, ElementNotFound
from robocorp.windows._ui_automation_wrapper import _UIAutomationControlWrapper
from robocorp.windows.protocols import Locator

if typing.TYPE_CHECKING:
    from PIL.Image import Image

    from robocorp.windows._iter_tree import ControlTreeNode
    from robocorp.windows.vendored.uiautomation.uiautomation import (
        Control,
        LegacyIAccessiblePattern,
        ValuePattern,
    )


PatternType = Union["ValuePattern", "LegacyIAccessiblePattern"]

DEFAULT_SEND_KEYS_INTERVAL = 0.01


class ISendKeys(Protocol):
    def SendKeys(
        self,
        text: str,
        interval: float = 0.01,
        waitTime: float = 1,
        charMode: bool = True,
        debug: bool = False,
    ) -> None:
        pass


def set_value_validator(expected: str, actual: str) -> bool:
    """Checks the passed against the final set value and returns status."""
    return actual.strip() == expected.strip()  # due to EOLs inconsistency


def _wait_time() -> float:
    from robocorp.windows import config

    return config().wait_time


def _simulate_move() -> bool:
    from robocorp.windows import config

    return config().simulate_mouse_movement


class ControlElement:
    """
    Class used to interact with a control.
    """

    logger = logging.getLogger(__name__)

    def __init__(self, wrapped: "_UIAutomationControlWrapper"):
        self._wrapped = wrapped
        self.location_info = self._wrapped.location_info

    @property
    def path(self) -> Optional[str]:
        """
        Provides the relative path in which this element was found

        Note: this is relative to the element which was used for the `find` or
        `find_window` and cannot be used as an absolute path to be used to find
        the control from the desktop.
        """
        return self.location_info.path

    def inspect(self) -> None:
        """
        Starts inspecting with this element as the root element upon which
        other elements will be found (i.e.: only elements under this element
        in the hierarchy will be inspected, other elements can only be inspected
        if the inspection root is changed).

        Example:

            ```python
            from robocorp import windows
            windows.find_window('Calculator').inspect()
            ```
        """
        from robocorp.windows._inspect import ElementInspector

        element_inspector = ElementInspector(self)
        element_inspector.inspect()

    def get_parent(self) -> Optional["ControlElement"]:
        """
        Returns:
            The parent element for this control.
        """
        parent = self._wrapped.get_parent()
        if parent is None:
            return None
        return ControlElement(parent)

    def is_same_as(self, other: "ControlElement") -> bool:
        """
        Args:
            other: The element to compare to.

        Returns:
            True if this elements points to the same element represented
            by the other control.
        """
        from robocorp.windows.vendored.uiautomation.uiautomation import ControlsAreSame

        return ControlsAreSame(self._wrapped.item, other._wrapped.item)

    def _find_ui_automation_wrapper(
        self,
        locator: Optional[Locator] = None,
        search_depth: int = 8,
        timeout: Optional[float] = None,
    ) -> "_UIAutomationControlWrapper":
        """
        Internal API to find the control to interact with.
        """
        from robocorp.windows._find_ui_automation import find_ui_automation_wrapper

        root = self._wrapped

        self.logger.info("Getting element with locator: %s", locator)
        if not locator:
            return root

        element = find_ui_automation_wrapper(
            locator, search_depth, timeout=timeout, root_element=root
        )
        self.logger.info("Returning element: %s", element)
        return element

    @property
    def ui_automation_control(self) -> "Control":
        """
        Provides the Control actually wrapped by this ControlElement.
        Can be used as an escape hatch if some functionality is not directly
        covered by this class (in general this API should only be used if
        a better API isn't directly available in the ControlElement).
        """
        return self._wrapped.item

    def is_disposed(self) -> bool:
        """
        Returns:
            True if the underlying control is already disposed and False
            otherwise.
        """
        try:
            self._wrapped.item.Name
        except COMError:
            return True
        else:
            return False

    @property
    def handle(self) -> int:
        """
        Returns:
            The internal native window handle from the control wrapped in this
            class.
        """
        return self._wrapped.handle

    def has_keyboard_focus(self) -> bool:
        """
        Returns:
            True if this control currently has keyboard focus.
        """
        return self._wrapped.item.HasKeyboardFocus

    @property
    def name(self) -> str:
        """
        Returns:
            The name of the underlying control wrapped in this class
            (matches the locator `name`).

        Note:
            This value is cached when the element is created and even if the
            related value of the underlying control changes the initial value
            found will still be returned.
        """
        return self._wrapped.name

    @property
    def automation_id(self) -> str:
        """
        Returns:
            The automation id of the underlying control wrapped in this class
            (matches the locator `automationid` or `id`).

        Note:
            This value is cached when the element is created and even if the
            related value of the underlying control changes the initial value
            found will still be returned.
        """
        return self._wrapped.automation_id

    @property
    def control_type(self) -> str:
        """
        Returns:
            The control type of the underlying control wrapped in this class
            (matches the locator `control` or `type`).

        Note:
            This value is cached when the element is created and even if the
            related value of the underlying control changes the initial value
            found will still be returned.
        """
        return self._wrapped.control_type

    @property
    def class_name(self) -> str:
        """
        Returns:
            The class name of the underlying control wrapped in this class
            (matches the locator `class`).

        Note:
            This value is cached when the element is created and even if the
            related value of the underlying control changes the initial value
            found will still be returned.
        """
        return self._wrapped.class_name

    @property
    def left(self) -> int:
        """
        Returns:
            The left bound of the control (-1 if invalid).

        Note:
            This value is cached when the element is created and even if the
            related value of the underlying control changes the initial value
            found will still be returned. The method `update_geometry()` may
            be used to get the new bounds of the control.
        """
        return self._wrapped.left

    @property
    def right(self) -> int:
        """
        Returns:
            The right bound of the control (-1 if invalid).

        Note:
            This value is cached when the element is created and even if the
            related value of the underlying control changes the initial value
            found will still be returned. The method `update_geometry()` may
            be used to get the new bounds of the control.
        """
        return self._wrapped.right

    @property
    def top(self) -> int:
        """
        Returns:
            The top bound of the control (-1 if invalid).

        Note:
            This value is cached when the element is created and even if the
            related value of the underlying control changes the initial value
            found will still be returned. The method `update_geometry()` may
            be used to get the new bounds of the control.
        """
        return self._wrapped.top

    @property
    def bottom(self) -> int:
        """
        Returns:
            The bottom bound of the control (-1 if invalid).

        Note:
            This value is cached when the element is created and even if the
            related value of the underlying control changes the initial value
            found will still be returned. The method `update_geometry()` may
            be used to get the new bounds of the control.
        """
        return self._wrapped.bottom

    @property
    def width(self) -> int:
        """
        Returns:
            The width of the control (-1 if invalid).

        Note:
            This value is cached when the element is created and even if the
            related value of the underlying control changes the initial value
            found will still be returned. The method `update_geometry()` may
            be used to get the new bounds of the control.
        """
        return self._wrapped.width

    @property
    def height(self) -> int:
        """
        Returns:
            The height of the control (-1 if invalid).

        Note:
            This value is cached when the element is created and even if the
            related value of the underlying control changes the initial value
            found will still be returned. The method `update_geometry()` may
            be used to get the new bounds of the control.
        """
        return self._wrapped.height

    @property
    def rectangle(self) -> Tuple[int, int, int, int]:
        """
        Returns:
            A tuple with (left, top, right, bottom) -- (all -1 if invalid).

        Note:
            This value is cached when the element is created and even if the
            related value of the underlying control changes the initial value
            found will still be returned. The method `update_geometry()` may
            be used to get the new bounds of the control.
        """
        return (self.left, self.top, self.right, self.bottom)

    @property
    def xcenter(self) -> int:
        """
        Returns:
            The x position of the center of the control (-1 if invalid).

        Note:
            This value is cached when the element is created and even if the
            related value of the underlying control changes the initial value
            found will still be returned. The method `update_geometry()` may
            be used to get the new bounds of the control.
        """
        return self._wrapped.xcenter

    @property
    def ycenter(self) -> int:
        """
        Returns:
            The y position of the center of the control (-1 if invalid).

        Note:
            This value is cached when the element is created and even if the
            related value of the underlying control changes the initial value
            found will still be returned. The method `update_geometry()` may
            be used to get the new bounds of the control.
        """
        return self._wrapped.ycenter

    def update_geometry(self) -> None:
        """
        This method may be called to update the cached coordinates of the
        control bounds.
        """
        self._wrapped.update_geometry()

    def __str__(self) -> str:
        # Print what can be used in the locator.
        handle = self.handle

        def fmt(s):
            s = str(s)
            if not s:
                return '""'

            if " " in s:
                s = f'"{s}"'
            return s

        # These are cached, so, no need for try..except here.
        location_info = self.location_info

        lst = []

        if location_info.query_locator:
            lst.append(f"locator:{location_info.query_locator}")

        if location_info.depth:
            lst.append(f"depth:{location_info.depth}")

        if location_info.child_pos:
            lst.append(f"index:{location_info.child_pos}")

        if location_info.path:
            lst.append(f"path:{location_info.path}")

        info = (
            f"control:{fmt(self.control_type)} "
            f"class:{fmt(self.class_name)} "
            f"name:{fmt(self.name)} "
            f"id:{fmt(self.automation_id)} "
            f"handle:0x{handle:X}({handle})"
        )
        if lst:
            s = " ".join(lst)

            info = f"{info} Search info({s})"
        return info

    def __repr__(self):
        return f"""{self.__class__.__name__}({self.__str__()})"""

    def find(
        self,
        locator: Locator,
        search_depth: int = 8,
        timeout: Optional[float] = None,
    ) -> "ControlElement":
        """
        This method may be used to find a control in the descendants of this
        control.

        The first matching element is returned.

        Args:
            locator: The locator to be used to search a child control.

            search_depth: Up to which depth the hierarchy should be searched.

            timeout:
                The search for a child with the given locator will be retried
                until the given timeout elapses.

                At least one full search up to the given depth will always be done
                and the timeout will only take place afterwards.

                If not given the global config timeout will be used.

        Raises:
            ElementNotFound if an element with the given locator could not be
            found.
        """
        try:
            return ControlElement(
                self._find_ui_automation_wrapper(locator, search_depth, timeout=timeout)
            )
        except ElementNotFound as e:
            from robocorp import windows

            config = windows.config()
            if not config.verbose_errors:
                raise

            # Verbose error
            msg = (
                f"Could not locate window with locator: {locator!r} "
                f"(timeout: {timeout if timeout is not None else config.timeout})"
            )
            child_elements_msg = ["\nChild Elements Found:"]
            for w in self._iter_children_nodes(max_depth=search_depth):
                child_elements_msg.append(str(w))

            msg += "\n".join(child_elements_msg)
            raise ElementNotFound(msg) from e

    def find_many(
        self,
        locator: Locator,
        search_depth: int = 8,
        timeout: Optional[float] = None,
        search_strategy: Literal["siblings", "all"] = "siblings",
        wait_for_element=False,
    ) -> List["ControlElement"]:
        """
        This method may be used to find multiple descendants of the current
        element matching the given locator.

        Args:
            locator: The locator that should be used to find elements.

            search_depth: Up to which depth the tree will be traversed.

            timeout:
                The search for a child with the given locator will be retried
                until the given timeout elapses.

                At least one full search up to the given depth will always be done
                and the timeout will only take place afterwards.

                If not given the global config timeout will be used.

                Only used if `wait_for_element` is True.

            search_strategy:
                The search strategy to be used to find elements.

                `siblings` means that after the first element is found, the tree
                    traversal should be stopped and only sibling elements will be
                    searched.

                `all` means that all the elements up to the given search depth
                    will be searched.

            wait_for_window: Defines whether the search should keep on searching
                until an element with the given locator is found (note that if True
                and no element was found an ElementNotFound is raised).

        Note:
            Keep in mind that by default the search strategy is for searching
            `siblings` of the initial element found (so, by default, after the first
            element is found a tree traversal is not done and only sibling elements
            from the initial element are found).
        """
        from robocorp.windows._find_ui_automation import find_ui_automation_wrappers

        return [
            ControlElement(x)
            for x in find_ui_automation_wrappers(
                locator,
                search_depth,
                root_element=self._wrapped,
                timeout=timeout,
                search_strategy=search_strategy,
                wait_for_element=wait_for_element,
            )
        ]

    def _iter_children_nodes(
        self, *, max_depth: int = 8
    ) -> Iterator["ControlTreeNode[ControlElement]"]:
        """
        Internal API to provide structure with a `ControlTreeNode` for printing.
        Not part of the public API (should not be used by client code).
        """

        from robocorp.windows._iter_tree import ControlTreeNode, iter_tree
        from robocorp.windows._ui_automation_wrapper import LocationInfo

        for el in iter_tree(self._wrapped.item, max_depth):
            location_info = LocationInfo(None, el.depth, el.child_pos, el.path)
            wrapper = _UIAutomationControlWrapper(el.control, location_info)
            if wrapper.is_disposed():
                continue

            yield ControlTreeNode(
                ControlElement(wrapper), el.depth, el.child_pos, el.path
            )

    def iter_children(self, *, max_depth: int = 8) -> Iterator["ControlElement"]:
        """
        Iterates over all of the children of this element up to the max_depth
        provided.

        Args:
            max_depth: the maximum depth which should be iterated to.

        Returns:
            An iterator of `ControlElement` which provides the descendants of
            this element.

        Note:
            Iteration over too many items can be slow. Try to keep the
            max depth up to a minimum to avoid slow iterations.
        """

        from robocorp.windows._iter_tree import iter_tree
        from robocorp.windows._ui_automation_wrapper import LocationInfo

        for el in iter_tree(self._wrapped.item, max_depth):
            location_info = LocationInfo(None, el.depth, el.child_pos, el.path)
            wrapper = _UIAutomationControlWrapper(el.control, location_info)
            if wrapper.is_disposed():
                continue

            yield ControlElement(wrapper)

    def print_tree(
        self, stream=None, show_properties: bool = False, max_depth: int = 8
    ) -> None:
        """
        Print a tree of control elements.

        A Windows application structure can contain multilevel element structure.
        Understanding this structure is crucial for creating locators. (based on
        controls' details and their parent-child relationship)

        This keyword can be used to output logs of application's element structure.

        The printed element attributes correspond to the values that may be used
        to create a locator to find the actual wanted element.

        Args:
            stream: The stream to which the text should be printed (if not given,
                sys.stdout is used).

            show_properties: Whether the properties of each element should
                be printed (off by default as it can be considerably slower
                and makes the output very verbose).

            max_depth: Up to which depth the tree should be printed.

        Example:

            Print the top-level window elements:

            ```python
            from robocorp import windows
            windows.desktop().print_tree()
            ```

        Example:

            Print the tree starting at some other element:

            ```python
            from robocorp import windows
            windows.find("Calculator > path:2|3").print_tree()
            ```
        """
        from robocorp.windows._iter_tree import ControlTreeNode

        if stream is None:
            stream = sys.stderr

        # Show the root.
        root = ControlTreeNode(self, 0, 0, "")
        iter_in = itertools.chain(
            (root,), self._iter_children_nodes(max_depth=max_depth)
        )

        if not show_properties:
            for child in iter_in:
                print(child, file=stream)
        else:
            for child in iter_in:
                print(child, file=stream)

                space = " " * ((child.depth * 4 + 2))
                control = child.control
                print(f"{space}Properties:", file=stream)
                try:
                    v = control.get_value()
                    print(f"  {space}get_value() = {v!r}", file=stream)
                except ActionNotPossible:
                    pass
                try:
                    v = control.get_text()
                    print(f"  {space}get_text() = {v!r}", file=stream)
                except ActionNotPossible:
                    pass

                ui_automation_control = control.ui_automation_control
                # Skip attributes which don't seem relevant.
                skip_attributes = {
                    "ValidKeys",
                    "CreateControlFromControl",
                    "CreateControlFromElement",
                    "searchDepth",
                    "searchFromControl",
                    "searchInterval",
                    "searchProperties",
                }
                for attr in dir(ui_automation_control):
                    if attr.startswith("_") or attr in skip_attributes:
                        continue
                    try:
                        try:
                            v = getattr(ui_automation_control, attr)
                        except AttributeError:
                            pass
                        else:
                            if v:
                                if inspect.ismethod(v):
                                    if not attr.startswith(
                                        "Is"
                                    ) and not attr.startswith("Has"):
                                        continue

                                    v = v()
                                    print(
                                        (
                                            f"  {space}ui_automation_control."
                                            f"{attr}() = {v}"
                                        ),
                                        file=stream,
                                    )
                                else:
                                    print(
                                        f"  {space}ui_automation_control.{attr} = {v}",
                                        file=stream,
                                    )
                    except ActionNotPossible:
                        pass

    def click(
        self,
        locator: Optional[Locator] = None,
        wait_time: Optional[float] = None,
        timeout: Optional[float] = None,
    ) -> _UIAutomationControlWrapper:
        """Mouse click on element matching given locator.

        Exception ``ActionNotPossible`` is raised if element does not
        allow Click action.

        :param locator: String locator or element object.
        :param wait_time: time to wait after click, default is a
         library `wait_time`, see keyword ``Set Wait Time``
        :param timeout: float value in seconds, see keyword
         ``Set Global Timeout``
        :return: _UIAutomationControlWrapper object

        Example:

        .. code-block:: robotframework

            Click  id:button1
            Click  id:button2 offset:10,10
            ${element}=  Click  name:SendButton  wait_time=5.0
        """
        return self._mouse_click(locator, "Click", wait_time, timeout)

    def double_click(
        self,
        locator: Locator,
        wait_time: Optional[float] = None,
        timeout: Optional[float] = None,
    ) -> _UIAutomationControlWrapper:
        """Double mouse click on element matching given locator.

        Exception ``ActionNotPossible`` is raised if element does not
        allow Click action.

        :param locator: String locator or element object.
        :param wait_time: time to wait after click, default is a
         library `wait_time`, see keyword ``Set Wait Time``
        :param timeout: float value in seconds, see keyword
         ``Set Global Timeout``
        :return: _UIAutomationControlWrapper object

        Example:

        .. code-block:: robotframework

            ${element}=  Double Click  name:ResetButton
        """
        return self._mouse_click(locator, "DoubleClick", wait_time, timeout)

    def right_click(
        self,
        locator: Locator,
        wait_time: Optional[float] = None,
        timeout: Optional[float] = None,
    ) -> _UIAutomationControlWrapper:
        """Right mouse click on element matching given locator.

        Exception ``ActionNotPossible`` is raised if element does not
        allow Click action.

        :param locator: String locator or element object.
        :param wait_time: time to wait after click, default is a
         library `wait_time`, see keyword ``Set Wait Time``
        :param timeout: float value in seconds, see keyword
         ``Set Global Timeout``
        :return: _UIAutomationControlWrapper object

        Example:

        .. code-block:: robotframework

            ${element}=  Right Click  name:MenuButton
        """
        return self._mouse_click(locator, "RightClick", wait_time, timeout)

    def middle_click(
        self,
        locator: Locator,
        wait_time: Optional[float] = None,
        timeout: Optional[float] = None,
    ) -> _UIAutomationControlWrapper:
        """Right mouse click on element matching given locator.

        Exception ``ActionNotPossible`` is raised if element does not
        allow Click action.

        :param locator: String locator or element object.
        :param wait_time: time to wait after click, default is a
         library `wait_time`, see keyword ``Set Wait Time``
        :param timeout: float value in seconds, see keyword
         ``Set Global Timeout``
        :return: _UIAutomationControlWrapper object

        Example:

        .. code-block:: robotframework

            ${element}=  Middle Click  name:button2
        """
        return self._mouse_click(locator, "MiddleClick", wait_time, timeout)

    def _mouse_click(
        self,
        locator: Optional[Locator],
        click_type: str,
        wait_time: Optional[float],
        timeout: Optional[float],
    ) -> _UIAutomationControlWrapper:
        click_wait_time: float = wait_time if wait_time is not None else _wait_time()
        element = self._find_ui_automation_wrapper(locator, timeout=timeout)
        self._click_element(element, click_type, click_wait_time)
        return element

    def _click_element(
        self,
        element: _UIAutomationControlWrapper,
        click_type: str,
        click_wait_time: float,
    ):
        item = element.item
        click_function = getattr(item, click_type, None)
        if not click_function:
            raise ActionNotPossible(
                f"Element {element!r} does not have {click_type!r} attribute"
            )
        # Get a new fresh bounding box each time, since the element might have been
        #  moved from its initial spot.
        rect = item.BoundingRectangle
        if not rect or rect.width() == 0 or rect.height() == 0:
            raise ActionNotPossible(
                f"Element {element!r} is not visible for clicking, use a string"
                " locator and ensure the root window is in focus"
            )

        log_message = f"{click_type}-ing element"

        self.logger.debug(log_message)
        click_function(
            # x=offset_x,
            # y=offset_y,
            simulateMove=_simulate_move(),
            waitTime=click_wait_time,
        )

    def select(
        self,
        locator: Locator,
        value: str,
        timeout: Optional[float] = None,
    ) -> _UIAutomationControlWrapper:
        """Select a value on the passed element if such action is supported.

        The ``ActionNotPossible`` exception is raised when the element does not allow
        the `Select` action. This is usually used with combo box elements.

        :param locator: String locator or element object.
        :param value: String value to select on Control element
        :returns: The controlled Windows element.

        **Example: Robot Framework**

            *** Settings ***
            Library     RPA.Windows

            *** Tasks ***
            Set Notepad Size
                Select    id:FontSizeComboBox    22

        **Example: Python**

        .. code-block:: python

            from RPA.Windows import Windows

            lib = Windows()

            def set_notepad_size():
                lib.select("id:FontSizeComboBox", "22")
        """
        element = self._find_ui_automation_wrapper(locator, timeout=timeout)
        if hasattr(element.item, "Select"):
            # NOTE(cmin764): This is not supposed to work on `*Pattern` or `TextRange`
            #  objects. (works with `Control`s and its derived flavors only, like a
            #  combobox)
            element.item.Select(
                value, simulateMove=_simulate_move(), waitTime=_wait_time()
            )
        else:
            raise ActionNotPossible(
                f"Element {locator!r} does not support selection (try with"
                " `Set Value` instead)"
            )
        return element

    def send_keys(
        self,
        locator: Optional[Locator] = None,
        keys: Optional[str] = None,
        interval: float = DEFAULT_SEND_KEYS_INTERVAL,
        wait_time: Optional[float] = None,
        send_enter: bool = False,
        timeout: Optional[float] = None,
    ):
        """Send keys to desktop, current window or to Control element
        defined by given locator.

        If ``locator`` is `None` then keys are sent to desktop.

        Exception ``ActionNotPossible`` is raised if element does not
        allow SendKeys action.

        :param locator: Optional string locator or element object.
        :param keys: The keys to send.
        :param interval: Time between each sent key. (defaults to 0.01 seconds)
        :param wait_time: Time to wait after sending all the keys. (defaults to
            library's set value, see keyword ``Set Wait Time``)
        :param send_enter: If `True` then the {Enter} key is pressed at the end of the
            sent keys.
        :returns: The element identified through `locator`.

        Example:

        .. code-block:: robotframework

            Send Keys  desktop   {Ctrl}{F4}
            Send Keys  keys={Ctrl}{F4}   # locator will be NONE, keys sent to desktop
            Send Keys  id:input5  username   send_enter=${True}
            ${element}=   Get Element   id:pass
            Send Keys  ${element}  password   send_enter=${True}
        """
        element: Union["_UIAutomationControlWrapper", ISendKeys]
        if locator:
            element = self._find_ui_automation_wrapper(locator, timeout=timeout)
        else:
            import robocorp.windows.vendored.uiautomation as auto

            element = auto
        return self._send_keys_to_element(
            element,
            keys or "",
            interval,
            wait_time,
            send_enter,
        )

    @classmethod
    def _send_keys_to_element(
        cls,
        element: Union["_UIAutomationControlWrapper", ISendKeys],
        keys: str,
        interval: float = DEFAULT_SEND_KEYS_INTERVAL,
        wait_time: Optional[float] = None,
        send_enter: bool = False,
    ):
        control: Union["Control", ISendKeys]
        if isinstance(element, _UIAutomationControlWrapper):
            control = element.item
        else:
            control = element

        if send_enter:
            keys += "{Enter}"
        if hasattr(control, "SendKeys"):
            if wait_time is None:
                wait_time = _wait_time()
            cls.logger.info("Sending keys %r to control: %s", keys, control)
            control.SendKeys(text=keys, interval=interval, waitTime=wait_time)
        else:
            loc = getattr(element, "locator", "<not specified>")
            raise ActionNotPossible(
                f"Element found with {loc!r} does not have " "SendKeys' attribute"
            )

    def get_text(
        self,
        locator: Optional[Locator] = None,
        timeout: Optional[float] = None,
    ) -> Optional[str]:
        """Get text from Control element defined by the locator.

        Exception ``ActionNotPossible`` is raised if element does not
        allow GetWindowText action.

        :param locator: String locator or element object.
        :return: value of WindowText attribute of an element

        Example:

        .. code-block:: robotframework

            ${date} =  Get Text   type:Edit name:"Date of birth"
        """
        element = self._find_ui_automation_wrapper(locator, timeout=timeout)
        if hasattr(element.item, "GetWindowText"):
            return element.item.GetWindowText()
        raise ActionNotPossible(
            f"Element found with {locator!r} does not have 'GetWindowText' attribute"
        )

    @staticmethod
    def get_value_pattern(
        element: _UIAutomationControlWrapper,
    ) -> Optional[Callable[[], PatternType]]:
        item: "Control" = element.item
        get_pattern: Optional[Callable] = getattr(
            item, "GetValuePattern", getattr(item, "GetLegacyIAccessiblePattern", None)
        )
        return get_pattern

    def get_value(
        self,
        locator: Optional[Locator] = None,
        timeout: Optional[float] = None,
    ) -> Optional[str]:
        """Get the value of the element defined by the provided `locator`.

        The ``ActionNotPossible`` exception is raised if the identified element doesn't
        support value retrieval.

        :param locator: String locator or element object.
        :returns: Optionally the value of the identified element.

        **Example: Robot Framework**

        .. code-block:: robotframework

            ${value} =   Get Value   type:DataItem name:column1

        **Example: Python**

        .. code-block:: python

            from RPA.Windows import Windows

            lib_win = Windows()
            text = lib_win.get_value("Rich Text Window")
            print(text)
        """
        element = self._find_ui_automation_wrapper(locator, timeout=timeout)
        get_value_pattern = self.get_value_pattern(element)

        if get_value_pattern:
            func_name = get_value_pattern.__name__
            self.logger.info(
                "Retrieving the element value with the %r method.", func_name
            )
            value_pattern = get_value_pattern()
            return value_pattern.Value if value_pattern else None

        raise ActionNotPossible(
            f"Element found with {locator!r} doesn't support value retrieval"
        )

    def _set_value_with_pattern(
        self,
        value: str,
        newline_string: str,
        *,
        action: str,
        get_value_pattern: Callable[[], PatternType],
        append: bool,
        locator: Optional[Locator],
        validator: Optional[Callable],
    ):
        func_name = get_value_pattern.__name__
        self.logger.info("%s the element value with the %r method.", action, func_name)
        value_pattern = get_value_pattern()
        current_value = value_pattern.Value if append else ""
        expected_value = f"{current_value}{value}{newline_string}"
        value_pattern.SetValue(expected_value)
        if validator and not validator(expected_value, value_pattern.Value):
            raise ValueError(
                f"Element found with {locator!r} couldn't set value: {expected_value}"
            )

    def _set_value_with_keys(
        self,
        value: str,
        newline_string: str,
        *,
        action: str,
        element: _UIAutomationControlWrapper,
        append: bool,
        locator: Optional[Locator],
        validator: Optional[Callable],
    ):
        self.logger.info(
            "%s the element value with `Send Keys`. (no patterns found)", action
        )
        if newline_string or re.search("[\r\n]", value):
            self.logger.warning(
                "The `newline` switch and EOLs are ignored when setting a value"
                " through keys! (insert them with the `enter` parameter only)"
            )
        get_text_pattern = getattr(element.item, "GetTextPattern", None)

        def get_text():
            return (
                get_text_pattern().DocumentRange.GetText() if get_text_pattern else None
            )

        if append:
            current_value: str = get_text() or ""
        else:
            # Delete the entire present value inside.
            self._send_keys_to_element(element, "{Ctrl}a{Del}")
            current_value = ""
        if value:
            self._send_keys_to_element(element, value)
            actual_value = get_text()
            if actual_value is not None:
                if validator and not validator(f"{current_value}{value}", actual_value):
                    raise ValueError(
                        f"Element found with {locator!r} couldn't send value"
                        f" through keys: {value}"
                    )

    def set_value(
        self,
        locator: Optional[Locator] = None,
        value: Optional[str] = None,
        append: bool = False,
        enter: bool = False,
        newline: bool = False,
        send_keys_fallback: bool = True,
        validator: Optional[Callable] = set_value_validator,
        timeout: Optional[float] = None,
    ) -> _UIAutomationControlWrapper:
        """Set value of the element defined by the locator.

        *Note:* An anchor will work only on element structures where you can
        rely on the stability of that root/child element tree, as remaining the same.
        Usually these kind of structures are tables. (but not restricted to)

        *Note:* It is important to set ``append=${True}`` if you want to keep the
        current text in the element. Other option is to read the current text into a
        variable, then modify that value as you wish and pass it to the ``Set Value``
        keyword for a complete text replacement. (without setting the `append` flag)

        The following exceptions may be raised:

            - ``ActionNotPossible`` if the element does not allow the `SetValue` action
              to be run on it nor having ``send_keys_fallback=${True}``.
            - ``ValueError`` if the new value to be set can't be set correctly.

        :param locator: String locator or element object.
        :param value: String value to be set.
        :param append: `False` for setting the value, `True` for appending it. (OFF by
            default)
        :param enter: Set it to `True` to press the *Enter* key at the end of the
            input. (nothing is pressed by default)
        :param newline: Set it to `True` to add a new line at the end of the value. (no
            EOL included by default; this won't work with `send_keys_fallback` enabled)
        :param send_keys_fallback: Tries to set the value by sending it through keys
            if the main way of setting it fails. (enabled by default)
        :param validator: Function receiving two parameters post-setting, the expected
            and the current value, which returns `True` if the two values match. (by
            default, the keyword will raise if the values are different, set this to
            `None` to disable validation or pass your custom function instead)
        :returns: The element object identified through the passed `locator`.

        **Example: Robot Framework**

        .. code-block:: robotframework

            *** Tasks ***
            Set Values In Notepad
                Set Value   type:DataItem name:column1   ab c  # Set value to "ab c"
                # Press ENTER after setting the value.
                Set Value    type:Edit name:"File name:"    console.txt   enter=${True}

                # Add newline (manually) at the end of the string. (Notepad example)
                Set Value    name:"Text Editor"  abc\\n
                # Add newline with parameter.
                Set Value    name:"Text Editor"  abc   newline=${True}

                # Clear Notepad window and start appending text.
                Set Anchor  name:"Text Editor"
                # All the following keyword calls will use the anchor element as a
                #  starting point, UNLESS they specify a locator explicitly or
                #  `Clear Anchor` is used.
                ${time} =    Get Time
                # Clears with `append=${False}`. (default)
                Set Value    value=The time now is ${time}
                # Append text and add a newline at the end.
                Set Value    value= and it's the task run time.   append=${True}
                ...    newline=${True}
                # Continue appending and ensure a new line at the end by pressing
                #  the Enter key this time.
                Set Value    value=But this will appear on the 2nd line now.
                ...    append=${True}   enter=${True}   validator=${None}

        **Example: Python**

        .. code-block:: python

            from RPA.Windows import Windows

            lib_win = Windows()
            locator = "Document - WordPad > Rich Text Window"
            elem = lib_win.set_value(locator, value="My text", send_keys_fallback=True)
            text = lib_win.get_value(elem)
            print(text)
        """
        value = value or ""
        if newline and enter:
            self.logger.warning(
                "Both `newline` and `enter` switches detected, expect to see multiple"
                " new lines in the final text content."
            )
        newline_string = "\n" if newline else ""
        element = self._find_ui_automation_wrapper(locator, timeout=timeout)
        get_value_pattern = self.get_value_pattern(element)
        action = "Appending" if append else "Setting"

        if get_value_pattern:
            self._set_value_with_pattern(
                value,
                newline_string,
                action=action,
                get_value_pattern=get_value_pattern,
                append=append,
                locator=locator,
                validator=validator,
            )
        elif send_keys_fallback:
            self._set_value_with_keys(
                value,
                newline_string,
                action=action,
                element=element,
                append=append,
                locator=locator,
                validator=validator,
            )
        else:
            raise ActionNotPossible(
                f"Element found with {locator!r} doesn't support value setting"
            )

        if enter:
            self.logger.info("Inserting a new line by sending the *Enter* key.")
            self._send_keys_to_element(
                element, "{Ctrl}{End}{Enter}", wait_time=_wait_time()
            )

        return element

    def screenshot_pil(
        self,
        locator: Optional[Locator] = None,
        search_depth: int = 8,
        timeout: Optional[float] = None,
    ) -> Optional["Image"]:
        from robocorp.windows._screenshot import screenshot

        el = self._find_ui_automation_wrapper(locator, search_depth, timeout=timeout)
        img = screenshot(el.item)
        if img is None:
            return None
        return img

    def screenshot(
        self,
        filename: Union[str, Path],
        locator: Optional[Locator] = None,
        search_depth: int = 8,
        img_format: str = "png",
        timeout: Optional[float] = None,
    ) -> Optional[str]:
        """Take a screenshot of the element defined by the locator.

        An `ActionNotPossible` exception is raised if the element doesn't allow being
        captured.

        :param locator: String locator or element object.
        :param filename: Image file name/path. (can be absolute/relative)
        :raises ActionNotPossible: When the element can't be captured.
        :returns: Absolute file path of the taken screenshot image.

        **Example: Robot Framework**

        .. code-block:: robotframework

            *** Tasks ***
            Take Screenshots
                Screenshot    desktop    desktop.png
                Screenshot    subname:Notepad    ${OUTPUT_DIR}${/}notepad.png

        **Example: Python**

        .. code-block:: python

            from RPA.Windows import Windows
            lib = Windows()

            def take_screenshots():
                lib.screenshot("desktop", "desktop.png")
                lib.screenshot("subname:Notepad", "output/notepad.png")
        """
        import os

        img = self.screenshot_pil(locator, search_depth, timeout)
        if img is None:
            return None

        location = os.path.abspath(str(filename))
        img.save(location, img_format)
        return location

    def log_screenshot(
        self,
        locator: Optional[Locator] = None,
        search_depth: int = 8,
        level="INFO",
        timeout: Optional[float] = None,
    ):
        from robocorp.log import html, suppress_variables

        from robocorp.windows._screenshot import screenshot_as_base64png

        el = self._find_ui_automation_wrapper(locator, search_depth, timeout=timeout)
        with suppress_variables():
            img_as_base64 = screenshot_as_base64png(el.item)
            if img_as_base64 is None:
                return None

            assert level in ("ERROR", "WARN", "INFO")

            html_contents = f"""<img src="data:image/png;base64,{img_as_base64}"/>"""
            html(html_contents, level)

    def set_focus(
        self,
        locator: Optional[Locator] = None,
        timeout: Optional[float] = None,
    ) -> None:
        """Set view focus to the element defined by the locator.

        :param locator: String locator or element object.

        Example:

        .. code-block:: robotframework

            Set Focus  name:Buy type:Button
        """
        element = self._find_ui_automation_wrapper(locator, timeout=timeout)
        if not hasattr(element.item, "SetFocus"):
            raise ActionNotPossible(
                f"Element found with {locator!r} does not have 'SetFocus' attribute"
            )
        element.item.SetFocus()

    def drag_and_drop(
        self,
        source_element: Locator,
        target_element: Locator,
        speed: float = 1.0,
        copy: Optional[bool] = False,
        wait_time: float = 1.0,
        timeout: Optional[float] = None,
    ):
        """Drag and drop the source element into target element.

        :param source: source element for the operation
        :param target: target element for the operation
        :param speed: adjust speed of operation, bigger value means more speed
        :param copy: on True does copy drag and drop, defaults to move
        :param wait_time: time to wait after drop, default 1.0 seconds

        Example:

        .. code-block:: robotframework

            # copying a file, report.html, from source (File Explorer) window
            # into a target (File Explorer) Window
            # locator
            Drag And Drop
            ...    name:C:\\temp type:Windows > name:report.html type:ListItem
            ...    name:%{USERPROFILE}\\Documents\\artifacts type:Windows > name:"Items View"
            ...    copy=True

        Example:

        .. code-block:: robotframework

            # moving *.txt files into subfolder within one (File Explorer) window
            ${source_dir}=    Set Variable    %{USERPROFILE}\\Documents\\test
            Control Window    name:${source_dir}
            ${files}=    Find Files    ${source_dir}${/}*.txt
            # first copy files to folder2
            FOR    ${file}    IN    @{files}
                Drag And Drop    name:${file.name}    name:folder2 type:ListItem    copy=True
            END
            # second move files to folder1
            FOR    ${file}    IN    @{files}
                Drag And Drop    name:${file.name}    name:folder1 type:ListItem
            END
        """  # noqa: E501
        import robocorp.windows.vendored.uiautomation as auto

        source = self._find_ui_automation_wrapper(source_element, timeout=timeout)
        target = self._find_ui_automation_wrapper(target_element, timeout=timeout)
        try:
            if copy:
                auto.PressKey(auto.Keys.VK_CONTROL)
            auto.DragDrop(
                source.xcenter,
                source.ycenter,
                target.xcenter,
                target.ycenter,
                moveSpeed=speed,
                waitTime=wait_time,
            )
        finally:
            if copy:
                click_wait_time: float = (
                    wait_time if wait_time is not None else _wait_time()
                )
                self._click_element(source, "Click", click_wait_time)
                auto.ReleaseKey(auto.Keys.VK_CONTROL)
