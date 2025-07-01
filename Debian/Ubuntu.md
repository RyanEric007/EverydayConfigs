# Ubuntu
---

Backup the existing profile and create the new one
```sh
mv ~/.bashrc ~/.bashrc.bak && vim ~/.bashrc
```
After you `sudo su`  for root
```sh
cp .bashrc ~/.bashrc && source ~/.bashrc
```

## .bashrc
```bash
# ~/.bashrc: executed by bash(1) for non-login shells.

# Exit if not running interactively
case $- in
    *i*) ;;
    *) return;;
esac

# History settings
HISTCONTROL=ignoreboth
shopt -s histappend
HISTSIZE=1000
HISTFILESIZE=2000

# Check window size after each command
shopt -s checkwinsize

# Enable recursive globbing (**)
shopt -s globstar

# Make less more friendly for non-text input files
[ -x /usr/bin/lesspipe ] && eval "$(SHELL=/bin/sh lesspipe)"

# Set variable identifying the chroot
if [ -z "${debian_chroot:-}" ] && [ -r /etc/debian_chroot ]; then
    debian_chroot=$(cat /etc/debian_chroot)
fi

# Determine if terminal supports color
case "$TERM" in
    xterm-color|*-256color) color_prompt=yes;;
esac

force_color_prompt=yes

if [ -n "$force_color_prompt" ]; then
    if [ -x /usr/bin/tput ] && tput setaf 1 >&/dev/null; then
        color_prompt=yes
    else
        color_prompt=
    fi
fi

# Prompt customization with emoji and newline
PROMPT_ALTERNATIVE=twoline
NEWLINE_BEFORE_PROMPT=yes

if [ "$color_prompt" = yes ]; then
    VIRTUAL_ENV_DISABLE_PROMPT=1
    prompt_color='\[\033[;32m\]'
    info_color='\[\033[1;34m\]'
    prompt_symbol=🐧

    if [ "$EUID" -eq 0 ]; then
        prompt_color='\[\033[;94m\]'
        info_color='\[\033[1;31m\]'
        prompt_symbol=💀
    fi

    case "$PROMPT_ALTERNATIVE" in
        twoline)
            PS1=${prompt_color}'┌──${debian_chroot:+($debian_chroot)──}'\
'${VIRTUAL_ENV:+(\[\033[0;1m\]$(basename "$VIRTUAL_ENV")'${prompt_color}')}'\
'('${info_color}'\u'${prompt_symbol}'\h'${prompt_color}')-[\[\033[0;1m\]\w'${prompt_color}']\n'\
'└─'${info_color}'\$ \[\033[0m\]';;
        oneline)
            PS1='${VIRTUAL_ENV:+($(basename "$VIRTUAL_ENV")) }${debian_chroot:+($debian_chroot)}'${info_color}'\u@\h\[\033[00m\]:'${prompt_color}'\[\033[01m\]\w\[\033[00m\]\$ ';;
        backtrack)
            PS1='${VIRTUAL_ENV:+($(basename "$VIRTUAL_ENV")) }${debian_chroot:+($debian_chroot)}\[\033[01;31m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ ';;
    esac

    unset prompt_color info_color prompt_symbol
else
    PS1='${debian_chroot:+($debian_chroot)}\u@\h:\w\$ '
fi

unset color_prompt force_color_prompt

# Set terminal title if supported
case "$TERM" in
xterm*|rxvt*|Eterm|aterm|kterm|gnome*|alacritty)
    PS1="\[\e]0;${debian_chroot:+($debian_chroot)}\u@\h: \w\a\]$PS1"
    ;;
*)
    ;;
esac

# Optional newline before prompt
[ "$NEWLINE_BEFORE_PROMPT" = yes ] && PROMPT_COMMAND="echo"

# Enable color support of ls, grep, diff, etc.
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


# Helpful Aliases
alias ls='ls --color=auto'
alias grep='grep --color=auto'
alias fgrep='fgrep --color=auto'
alias egrep='egrep --color=auto'
alias diff='diff --color=auto'
alias ip='ip --color=auto'
alias ll='ls --color=auto -rthla'
alias lll='ls --color=auto -lh --group-directories-first'
alias la='ls --color=auto -A'
alias l='ls --color=auto -CF'
alias rm='rm -i'
alias mv='mv -i'
alias cp='cp -i'
alias c='clear'
alias myip='curl checkip.amazonaws.com'
alias ports='sudo lsof -i -P -n | grep LISTEN'
alias py='python3'
alias ipy='ipython3'
alias u='sudo apt update && sudo apt full-upgrade -y && sudo apt autoremove -y && sudo apt autoclean -y && sudo apt clean && sudo apt dist-upgrade -y'

#alias n='sudo nala update && sudo nala upgrade -y --full && sudo nala autoremove && sudo nala clean'

# For .bash_aliases
if [ -f ~/.bash_aliases ]; then
    . ~/.bash_aliases
fi

# Enable programmable completion
# sudo apt install bash-completion -y
if ! shopt -oq posix; then
    if [ -f /usr/share/bash-completion/bash_completion ]; then
        . /usr/share/bash-completion/bash_completion
    elif [ -f /etc/bash_completion ]; then
        . /etc/bash_completion
    fi
fi
```