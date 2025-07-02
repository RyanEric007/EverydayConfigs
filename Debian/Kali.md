# Kali
---

Backup the existing profile and create the new one
```sh
mv ~/.zshrc ~/.zshrc.bak && vim ~/.zshrc
```

## .bashrc
```bash
# ~/.zshrc - Customized for Kali Linux 2025.2

# --------------------------------------------------------
# Shell options for usability
# --------------------------------------------------------

setopt autocd              # allow changing directories by typing the path
setopt interactivecomments # allow comments in interactive shell
setopt magicequalsubst     # expand foo=bar patterns in arguments
setopt nonomatch           # avoid errors for unmatched globs
setopt notify              # report background jobs immediately
setopt numericglobsort     # sort file lists numerically
setopt promptsubst         # allow prompt variables to expand dynamically

WORDCHARS='_-'             # treat these as word characters
PROMPT_EOL_MARK=""         # suppress % at line endings

# --------------------------------------------------------
# Key bindings
# --------------------------------------------------------

bindkey -e                                        # use emacs-style keybindings
bindkey ' ' magic-space                           # expand history on space
bindkey '^U' backward-kill-line                   # ctrl+U deletes whole line
bindkey '^[[3;5~' kill-word                       # ctrl+Del kills word
bindkey '^[[3~' delete-char                       # Del
bindkey '^[[1;5C' forward-word                    # ctrl+Right
bindkey '^[[1;5D' backward-word                   # ctrl+Left
bindkey '^[[5~' beginning-of-buffer-or-history    # PageUp
bindkey '^[[6~' end-of-buffer-or-history          # PageDown
bindkey '^[[H' beginning-of-line                  # Home
bindkey '^[[F' end-of-line                        # End
bindkey '^[[Z' undo                               # Shift+Tab undo

# --------------------------------------------------------
# Completion System
# --------------------------------------------------------

autoload -Uz compinit
compinit -d ~/.cache/zcompdump

# Use advanced completion styles
zstyle ':completion:*:*:*:*:*' menu select
zstyle ':completion:*' auto-description 'specify: %d'
zstyle ':completion:*' completer _expand _complete
zstyle ':completion:*' format 'Completing %d'
zstyle ':completion:*' group-name ''
zstyle ':completion:*' list-colors ''
zstyle ':completion:*' list-prompt %SAt %p: Hit TAB for more, or the character to insert%s
zstyle ':completion:*' matcher-list 'm:{a-zA-Z}={A-Za-z}'
zstyle ':completion:*' rehash true
zstyle ':completion:*' select-prompt %SScrolling active: current selection at %p%s
zstyle ':completion:*' use-compctl false
zstyle ':completion:*' verbose true
zstyle ':completion:*:kill:*' command 'ps -u $USER -o pid,%cpu,tty,cputime,cmd'

# Enable color in completions using LS_COLORS
if [ -x /usr/bin/dircolors ]; then
    test -r ~/.dircolors && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
    export LS_COLORS="$LS_COLORS:ow=30;44:"
    zstyle ':completion:*' list-colors "${(s.:.)LS_COLORS}"
    zstyle ':completion:*:*:kill:*:processes' list-colors '=(#b) #([0-9]#)*=0=01;31'
fi

# --------------------------------------------------------
# History configuration
# --------------------------------------------------------

HISTFILE=~/.zsh_history
HISTSIZE=1000
SAVEHIST=2000
setopt hist_expire_dups_first
setopt hist_ignore_dups
setopt hist_ignore_space
setopt hist_verify

alias history="history 0"

# --------------------------------------------------------
# Terminal window title
# --------------------------------------------------------

case "$TERM" in
    xterm*|rxvt*|Eterm|aterm|kterm|gnome*|alacritty)
        TERM_TITLE=$'\e]0;${debian_chroot:+($debian_chroot)}${VIRTUAL_ENV:+($(basename $VIRTUAL_ENV))}%n@%m: %~\a'
        ;;
    *)
        TERM_TITLE=""
        ;;
esac

precmd() {
    print -Pnr -- "$TERM_TITLE"
    if [ "$NEWLINE_BEFORE_PROMPT" = yes ]; then
        if [ -z "$_NEW_LINE_BEFORE_PROMPT" ]; then
            _NEW_LINE_BEFORE_PROMPT=1
        else
            print ""
        fi
    fi
}

# --------------------------------------------------------
# Prompt configuration
# --------------------------------------------------------

# Detect chroot (for Debian/Kali)
if [ -z "${debian_chroot:-}" ] && [ -r /etc/debian_chroot ]; then
    debian_chroot=$(cat /etc/debian_chroot)
fi

force_color_prompt=yes

configure_prompt() {
    prompt_symbol=㉿

    case "$PROMPT_ALTERNATIVE" in
        twoline)
            PROMPT=$'%F{%(#.blue.green)}┌──${debian_chroot:+($debian_chroot)─}${VIRTUAL_ENV:+($(basename $VIRTUAL_ENV))─}(%B%F{%(#.red.blue)}%n'$prompt_symbol$'%m%b%F{%(#.blue.green)})-[%B%F{reset}%(6~.%-1~/…/%4~.%5~)%b%F{%(#.blue.green)}]\n└─%B%(#.%F{red}#.%F{blue}$)%b%F{reset} '
            ;;
        oneline)
            PROMPT=$'${debian_chroot:+($debian_chroot)}${VIRTUAL_ENV:+($(basename $VIRTUAL_ENV))}%B%F{%(#.red.blue)}%n@%m%b%F{reset}:%B%F{%(#.blue.green)}%~%b%F{reset}%(#.#.$) '
            ;;
        backtrack)
            PROMPT=$'${debian_chroot:+($debian_chroot)}${VIRTUAL_ENV:+($(basename $VIRTUAL_ENV))}%B%F{red}%n@%m%b%F{reset}:%B%F{blue}%~%b%F{reset}%(#.#.$) '
            ;;
    esac

    unset prompt_symbol
}

PROMPT_ALTERNATIVE=twoline
NEWLINE_BEFORE_PROMPT=yes

if [ "$force_color_prompt" = yes ]; then
    VIRTUAL_ENV_DISABLE_PROMPT=1
    configure_prompt

    # Syntax highlighting
    if [ -f /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ]; then
        . /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
        ZSH_HIGHLIGHT_HIGHLIGHTERS=(main brackets pattern)
        ZSH_HIGHLIGHT_STYLES[default]=none
        ZSH_HIGHLIGHT_STYLES[unknown-token]=underline
        ZSH_HIGHLIGHT_STYLES[reserved-word]='fg=cyan,bold'
        ZSH_HIGHLIGHT_STYLES[suffix-alias]='fg=green,underline'
        ZSH_HIGHLIGHT_STYLES[global-alias]='fg=green,bold'
        ZSH_HIGHLIGHT_STYLES[precommand]='fg=green,underline'
        ZSH_HIGHLIGHT_STYLES[commandseparator]='fg=blue,bold'
        ZSH_HIGHLIGHT_STYLES[autodirectory]='fg=green,underline'
        ZSH_HIGHLIGHT_STYLES[path]=bold
        ZSH_HIGHLIGHT_STYLES[globbing]='fg=blue,bold'
        ZSH_HIGHLIGHT_STYLES[history-expansion]='fg=blue,bold'
        ZSH_HIGHLIGHT_STYLES[command-substitution]=none
        ZSH_HIGHLIGHT_STYLES[command-substitution-delimiter]='fg=magenta,bold'
        ZSH_HIGHLIGHT_STYLES[process-substitution]=none
        ZSH_HIGHLIGHT_STYLES[process-substitution-delimiter]='fg=magenta,bold'
        ZSH_HIGHLIGHT_STYLES[single-hyphen-option]='fg=green'
        ZSH_HIGHLIGHT_STYLES[double-hyphen-option]='fg=green'
        ZSH_HIGHLIGHT_STYLES[back-quoted-argument]=none
        ZSH_HIGHLIGHT_STYLES[single-quoted-argument]='fg=yellow'
        ZSH_HIGHLIGHT_STYLES[double-quoted-argument]='fg=yellow'
        ZSH_HIGHLIGHT_STYLES[dollar-quoted-argument]='fg=yellow'
        ZSH_HIGHLIGHT_STYLES[rc-quote]='fg=magenta'
        ZSH_HIGHLIGHT_STYLES[assign]=none
        ZSH_HIGHLIGHT_STYLES[redirection]='fg=blue,bold'
        ZSH_HIGHLIGHT_STYLES[comment]='fg=black,bold'
        ZSH_HIGHLIGHT_STYLES[arg0]='fg=cyan'
        ZSH_HIGHLIGHT_STYLES[bracket-error]='fg=red,bold'
        ZSH_HIGHLIGHT_STYLES[bracket-level-1]='fg=blue,bold'
        ZSH_HIGHLIGHT_STYLES[bracket-level-2]='fg=green,bold'
        ZSH_HIGHLIGHT_STYLES[bracket-level-3]='fg=magenta,bold'
        ZSH_HIGHLIGHT_STYLES[bracket-level-4]='fg=yellow,bold'
        ZSH_HIGHLIGHT_STYLES[bracket-level-5]='fg=cyan,bold'
        ZSH_HIGHLIGHT_STYLES[cursor-matchingbracket]=standout
    fi
else
    PROMPT='${debian_chroot:+($debian_chroot)}%n@%m:%~%(#.#.$) '
fi

unset color_prompt force_color_prompt

toggle_oneline_prompt(){
    if [ "$PROMPT_ALTERNATIVE" = oneline ]; then
        PROMPT_ALTERNATIVE=twoline
    else
        PROMPT_ALTERNATIVE=oneline
    fi
    configure_prompt
    zle reset-prompt
}
zle -N toggle_oneline_prompt
bindkey ^P toggle_oneline_prompt

# --------------------------------------------------------
# Less and man colors
# --------------------------------------------------------

export LESS_TERMCAP_mb=$'\E[1;31m'
export LESS_TERMCAP_md=$'\E[1;36m'
export LESS_TERMCAP_me=$'\E[0m'
export LESS_TERMCAP_so=$'\E[01;33m'
export LESS_TERMCAP_se=$'\E[0m'
export LESS_TERMCAP_us=$'\E[1;32m'
export LESS_TERMCAP_ue=$'\E[0m'

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

# System updates (Kali/apt)
alias u='sudo apt update && sudo apt full-upgrade -y && sudo apt autoremove -y && sudo apt autoclean -y && sudo apt clean && sudo apt dist-upgrade -y'

# Miscellaneous
alias c='clear'
alias q='exit'
alias mkd='mkdir -p'
alias path='print -l $path'
alias g='git'
alias v='vim'
alias h='history'

# --------------------------------------------------------
# Editor & Pager
# --------------------------------------------------------

export EDITOR=vim
export VISUAL=vim
export PAGER=less

# --------------------------------------------------------
# Plugins and Extras
# --------------------------------------------------------

# Zsh autosuggestions
if [ -f /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh ]; then
    . /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh
    ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE='fg=#999'
fi

# Command-not-found handler
if [ -f /etc/zsh_command_not_found ]; then
    . /etc/zsh_command_not_found
fi

# Load optional aliases
[[ -f ~/.zsh_aliases ]] && source ~/.zsh_aliases

```

Test and set:
```bash
source ~/.zshrc
```

After you `sudo su`  for root
```sh
cp .zshrc ~/.zshrc && source ~/.zshrc
```
