# Music Management Tools

This is a collection of things I use to manage my media. I collect a lot of
live shows and find working with all the files via the command line much
easier.

Note: None of these will work out of the box for you. They contain hard-coded
paths and server names that are specific to my environment. But they'll work
well as a place for you to start.

# zsh Functions

You can add the `zsh/functions` directory to your zsh setup to gain access to
some useful shell functions for listing out metadata in FLAC files and
converting FLAC to ALAC.

You can do this by adding the the `zsh/functions` directory to your `fpath` and
then running `autoload` all in your zshrc file. Something like this:

    fpath=("/path/to/where/repo/is/checked/out/zsh/functions" $fpath)
    # Autoload all functions in the functions directory
    autoload -Uz /path/to/where/repo/is/checked/out/zsh/functions/*(:t)


# Additional Requirements

You'll want to have the following things installed locally through whatever means you use to manage local installations:

* [ffmpeg](https://github.com/FFmpeg/FFmpeg)
* [rsync](https://linux.die.net/man/1/rsync)

# See Also

* [My dotfiles](https://github.com/ianchesal/dotfiles) -- lots of interesting stuff there
