## Minimal fixture game for the control-flow spike.
## Two labels, a store variable, a pause, and a menu.

default x = 0
default y = 0
default choice_made = ""

label start:
    "This is the start label."
    return

label set_x:
    $ x = 42
    "x has been set."

label set_y:
    $ y = 99
    pause

label menu_test:
    menu:
        "Pick a fruit:"
        "Apple":
            $ choice_made = "apple"
        "Banana":
            $ choice_made = "banana"
    "You chose [choice_made]."
