# Notes For Building / Running

My workflow is usually something like:

```
nvim .
# hack hack hack
just devel
```

This builds, installs and launches a special version of the Flatpak named `land.arcana.TarotCanvas.Devel` that has its own metadata and app data.

This sandboxing is useful so that testing new code doesn't mess with my own personal data.

### Profiles

The build system also supports setting up different "profiles" that I use to test various scenarios and stores them in `~/.var/appland.arcana.TarotCanvas.Devel/profiles.`
For example, if I want to test the app as a hypothetical power-user, I could establish a profile called "power-user" and run the app like so:

```
just devel-as power-user
```

This will setup a persistent profile that I can use to exercise the code that I am working on.

Or, if I want to test as a new user:

```
just devel-as fresh
```

The "fresh" profile is a special profile that is always empty.

