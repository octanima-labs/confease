Core API
========

.. currentmodule:: confease

The core API is centered on :class:`Confease`, a configuration container that stores :class:`Confitem` values with an origin and resolves conflicts through configurable precedence.

This reference is generated from the source docstrings using Sphinx autodoc.
See :doc:`../configuration` for manual editing, template defaults, reset
behavior, and migration from the removed editing ``user_only`` argument.

Origins
-------

.. data:: CLI

   Origin name for values loaded from command-line arguments.

.. data:: ENV

   Origin name for values loaded from environment variables.

.. data:: SYS

   Origin name for values loaded from configuration files outside the current user's home directory.

.. data:: USR

   Origin name for values loaded from user configuration files or assigned through :meth:`Confease.set`.

.. data:: DEF

   Origin name for defaults supplied through ``items`` or configured template values.

.. data:: ORIGINS

   Ordered list of all supported origin names.

Confease
--------

.. autoclass:: Confease
   :members:
   :special-members: __getitem__, __setitem__
   :exclude-members: __weakref__

Confitem
--------

.. autoclass:: Confitem
   :members:
   :special-members: __eq__, __repr__, __str__
   :exclude-members: __weakref__
