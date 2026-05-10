## Minimal Ren'Py game for CI testing.
## Exercises: label navigation, variable access, menu interaction, attributes.

default x = 0
default y = 0
default choice_made = ""
default visited_start = False

label start:
    $ visited_start = True
    "Welcome to the CI test game."
    return

label set_vars:
    $ x = 42
    $ y = 99
    "Variables set."
    return

label menu_test:
    menu:
        "Pick a fruit:"
        "Apple":
            $ choice_made = "apple"
        "Banana":
            $ choice_made = "banana"
    "You picked [choice_made]."
    return

label multi_step:
    $ x = 1
    "Step one."
    $ x = 2
    "Step two."
    $ x = 3
    "Done."
    return
