# Fedora
---

Backup the existing profile and create the new one
```sh
mv ~/.bashrc ~/.bashrc.bak && vim ~/.bashrc
```

## .bashrc
```bash
# ~/.bashrc - Customized for Fedora 40+

# --------------------------------------------------------
# Exit if not running interactively
# --------------------------------------------------------
case $- in
    *i*) ;;
    *) return ;;
esac

# --------------------------------------------------------
# Source global definitions
# --------------------------------------------------------

if [ -f /etc/bashrc ]; then
    . /etc/bashrc
fi

# --------------------------------------------------------
# Add user's bin directories to PATH
# --------------------------------------------------------

if ! [[ "$PATH" == *"$HOME/.local/bin:$HOME/bin"* ]]; then
    PATH="$HOME/.local/bin:$HOME/bin:$PATH"
fi
export PATH

# --------------------------------------------------------
# Load per-user extensions
# --------------------------------------------------------

if [ -d ~/.bashrc.d ]; then
    for rc in ~/.bashrc.d/*; do
        if [ -f "$rc" ]; then
            . "$rc"
        fi
    done
fi
unset rc

# --------------------------------------------------------
# Shell options
# --------------------------------------------------------

HISTCONTROL=ignoreboth
shopt -s histappend
shopt -s checkwinsize
shopt -s globstar

HISTSIZE=1000
HISTFILESIZE=2000

# Always show history numbers
alias h='history'
alias history='history 0'

# --------------------------------------------------------
# Lesspipe for non-text file preview
# --------------------------------------------------------

[ -x /usr/bin/lesspipe.sh ] && eval "$(SHELL=/bin/sh lesspipe.sh)"

# --------------------------------------------------------
# Detect chroot/container name
# --------------------------------------------------------

if [ -z "${CHROOT_NAME:-}" ] && [ -r /etc/fedora_chroot ]; then
    CHROOT_NAME=$(cat /etc/fedora_chroot)
fi

# --------------------------------------------------------
# Terminal window title
# --------------------------------------------------------

case "$TERM" in
    xterm*|rxvt*|Eterm|aterm|kterm|gnome*|alacritty)
        TERM_TITLE="\[\e]0;\${CHROOT_NAME:+(\$CHROOT_NAME)}\u@\h: \w\a\]"
        ;;
    *)
        TERM_TITLE=""
        ;;
esac

# --------------------------------------------------------
# Prompt configuration
# --------------------------------------------------------

force_color_prompt=yes
PROMPT_ALTERNATIVE=twoline
NEWLINE_BEFORE_PROMPT=yes

configure_prompt() {
    prompt_color='\[\033[;32m\]'
    info_color='\[\033[1;34m\]'
    prompt_symbol='🐧'
    reset_color='\[\033[0m\]'

    if [ "$EUID" -eq 0 ]; then
        prompt_color='\[\033[;94m\]'
        info_color='\[\033[1;31m\]'
        prompt_symbol='💀'
    fi

    case "$PROMPT_ALTERNATIVE" in
        twoline)
            PS1=${TERM_TITLE}${prompt_color}'┌──'\
'${CHROOT_NAME:+($CHROOT_NAME)──}'\
'${VIRTUAL_ENV:+(\[\033[0;1m\]$(basename "$VIRTUAL_ENV")'${prompt_color}')}'\
'('${info_color}'\u'${prompt_symbol}'\h'${prompt_color}')-[\[\033[0;1m\]\w'${prompt_color}']\n'\
'└─'${info_color}'\$ '${reset_color}
            ;;
        oneline)
            PS1=${TERM_TITLE}'${VIRTUAL_ENV:+($(basename "$VIRTUAL_ENV")) }'\
'${CHROOT_NAME:+($CHROOT_NAME)}'\
${info_color}'\u@\h'${reset_color}':'${prompt_color}'\w'${reset_color}'\$ '
            ;;
        backtrack)
            PS1=${TERM_TITLE}'${VIRTUAL_ENV:+($(basename "$VIRTUAL_ENV")) }'\
'${CHROOT_NAME:+($CHROOT_NAME)}'\
'\[\033[01;31m\]\u@\h\[\033[00m\]:'\
'\[\033[01;34m\]\w\[\033[00m\]\$ '
            ;;
    esac
}

if [ "$force_color_prompt" = yes ]; then
    VIRTUAL_ENV_DISABLE_PROMPT=1
    configure_prompt
else
    PS1='${CHROOT_NAME:+($CHROOT_NAME)}\u@\h:\w\$ '
fi

# Optional newline before prompt
if [ "$NEWLINE_BEFORE_PROMPT" = yes ]; then
    PROMPT_COMMAND='echo'
fi

# Toggle prompt style (Ctrl+P)
toggle_oneline_prompt() {
    if [ "$PROMPT_ALTERNATIVE" = oneline ]; then
        PROMPT_ALTERNATIVE=twoline
    else
        PROMPT_ALTERNATIVE=oneline
    fi
    configure_prompt
}
bind '"\C-p":"\C-u$(toggle_oneline_prompt)\n"'

# --------------------------------------------------------
# Color support for common commands
# --------------------------------------------------------

if [ -x /usr/bin/dircolors ]; then
    test -r ~/.dircolors && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
    export LS_COLORS="$LS_COLORS:ow=30;44:"

    export LESS_TERMCAP_mb=$'\E[1;31m'
    export LESS_TERMCAP_md=$'\E[1;36m'
    export LESS_TERMCAP_me=$'\E[0m'
    export LESS_TERMCAP_so=$'\E[01;33m'
    export LESS_TERMCAP_se=$'\E[0m'
    export LESS_TERMCAP_us=$'\E[1;32m'
    export LESS_TERMCAP_ue=$'\E[0m'
fi

# --------------------------------------------------------
# Aliases
# --------------------------------------------------------

# Safer file operations
alias rm='rm -i'
alias cp='cp -i'
alias mv='mv -i'

# Colorful and detailed ls
alias ls='ls --color=auto'
alias ll='ls --color=auto -rthla'
alias lll='ls --color=auto -lh --group-directories-first'
alias la='ls --color=auto -A'
alias l='ls --color=auto -CF'
alias lt='ls --color=auto -ltrh'

# Networking tools
alias ip='ip --color=auto'
alias myip='curl -s checkip.amazonaws.com'
alias ports='sudo lsof -i -P -n | grep LISTEN'

# Grep, diff, etc.
alias grep='grep --color=auto'
alias egrep='grep -E --color=auto'
alias fgrep='grep -F --color=auto'
alias diff='diff --color=auto'

# Python
alias py='python3'
alias ipy='ipython3'
alias pip='pip3'

# Navigation
alias ..='cd ..'
alias ...='cd ../..'

# System updates (Fedora/DNF)
alias u='sudo dnf update -y && sudo dnf upgrade -y && sudo dnf autoremove -y && sudo dnf clean all'
# alias n='sudo nala update && sudo nala upgrade -y --full && sudo nala autoremove && sudo nala clean'

# Miscellaneous
alias c='clear'
alias q='exit'
alias mkd='mkdir -p'
alias path='echo $PATH | tr ":" "\n"'
alias g='git'
alias v='vim'

# --------------------------------------------------------
# Editor & Pager
# --------------------------------------------------------

export EDITOR=vim
export VISUAL=vim
export PAGER=less

# --------------------------------------------------------
# Plugins and Extras
# --------------------------------------------------------

# Load .bash_aliases if it exists
if [ -f ~/.bash_aliases ]; then
    . ~/.bash_aliases
fi

# Bash programmable completion
if ! shopt -oq posix; then
    if [ -f /usr/share/bash-completion/bash_completion ]; then
        . /usr/share/bash-completion/bash_completion
    elif [ -f /etc/bash_completion ]; then
        . /etc/bash_completion
    fi
fi
```

Test and set:
```bash
source ~/.bashrc
```

Then use `sudo su` to switch to root at current path and use:
```sh
cp .bashrc ~/.bashrc && source ~/.bashrc
```
