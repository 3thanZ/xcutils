"""xccopy: stream objects between cloud blob stores.

Copies an object from a source blob URI to a destination blob URI, streaming the
bytes in bounded chunks so arbitrarily large objects transfer with predictable
memory use. Authentication is always via the cloud CLIs (see xcutils_common.auth).
"""
