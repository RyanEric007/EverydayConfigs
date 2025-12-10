# ~/.bashrc - Optimized for AlmaLinux 10

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
        [ -f "$rc" ] && . "$rc"
    done
fi
unset rc

# --------------------------------------------------------
# Shell options & history settings
# --------------------------------------------------------
HISTCONTROL=ignoreboth
HISTSIZE=5000
HISTFILESIZE=10000
HISTFILE="$HOME/.bash_history"

shopt -s histappend
shopt -s checkwinsize
shopt -s globstar

alias h='history'

# --------------------------------------------------------
# Lesspipe (Alma uses lesspipe.sh)
# --------------------------------------------------------
[ -x /usr/bin/lesspipe.sh ] && eval "$(SHELL=/bin/sh lesspipe.sh)"

# --------------------------------------------------------
# Chroot/Container Detection (AlmaLinux)
# --------------------------------------------------------
if [ -z "${CHROOT_NAME:-}" ] && [ -r /etc/almalinux-release ]; then
    CHROOT_NAME="alma10"
fi

# --------------------------------------------------------
# Terminal Window Title
# --------------------------------------------------------
case "$TERM" in
    xterm*|rxvt*|gnome*|alacritty|tmux*)
        TERM_TITLE="\[\e]0;\${CHROOT_NAME:+(\$CHROOT_NAME)}\u@\h: \w\a\]"
        ;;
    *)
        TERM_TITLE=""
        ;;
esac

# --------------------------------------------------------
# Prompt Configuration
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
    esac
}

if [ "$force_color_prompt" = yes ]; then
    VIRTUAL_ENV_DISABLE_PROMPT=1
    configure_prompt
else
    PS1='${CHROOT_NAME:+($CHROOT_NAME)}\u@\h:\w\$ '
fi

# --------------------------------------------------------
# PROMPT_COMMAND: newline + save history each command
# --------------------------------------------------------
if [ "$NEWLINE_BEFORE_PROMPT" = yes ]; then
    PROMPT_COMMAND='history -a; history -n; echo'
fi

# Toggle prompt (Ctrl+P)
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
# Color Support
# --------------------------------------------------------
if [ -x /usr/bin/dircolors ]; then
    test -r ~/.dircolors && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
    export LS_COLORS="$LS_COLORS:ow=30;44:"
fi

# --------------------------------------------------------
# Aliases
# --------------------------------------------------------
alias rm='rm -i'
alias cp='cp -i'
alias mv='mv -i'

alias ls='ls --color=auto'
alias ll='ls --color=auto -rthla'
alias lll='ls --color=auto -lh --group-directories-first'
alias la='ls --color=auto -A'
alias l='ls --color=auto -CF'
alias lt='ls --color=auto -ltrh'

alias ip='ip --color=auto'

alias grep='grep --color=auto'
alias diff='diff --color=auto'

alias ..='cd ..'
alias ...='cd ../..'

alias py='python3'
alias pip='pip3'

alias c='clear'
alias q='exit'
alias mkd='mkdir -p'
alias path='echo $PATH | tr ":" "\n"'
alias g='git'
alias v='vim'

alias u='sudo dnf update -y && sudo dnf upgrade -y && sudo dnf autoremove -y && sudo dnf clean all'

# --------------------------------------------------------
# Editor & Pager
# --------------------------------------------------------
export EDITOR=vim
export VISUAL=vim
export PAGER=less

# --------------------------------------------------------
# Optional Aliases File
# --------------------------------------------------------
if [ -f ~/.bash_aliases ]; then
    . ~/.bash_aliases
fi

# --------------------------------------------------------
# Bash Completion (RHEL/Alma Standard Path)
# --------------------------------------------------------
if ! shopt -oq posix; then
    if [ -f /usr/share/bash-completion/bash_completion ]; then
        . /usr/share/bash-completion/bash_completion
    fi
fi
