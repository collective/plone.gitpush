Introduction
============

Integration between git and ``plone.resource``. It allows you to push and pull
files via git into a plone site via the git smart http protocol.
On push it can checkout.


#TODO. Work in progress - ZODB implementation of MemoryObjectStore

Currently provides a @@git view on the portal_resources which implements the Git smart http protocol. Goal would be to
allow:

  git push http://localhost:8080/Plone/portal_resources/@@git/themes/mytheme
  
  git pull http://localhost:8080/Plone/portal_resources/@@git/themes/mytheme
  
Any changes made via the p.a.theming online will become commits.

It should be possible for a user to checkout a branch of a resourse via the web so that alternative versions of a theme 
can be previewed online if needed.
