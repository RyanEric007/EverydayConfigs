# ZSH for macOS
---

Check your shells:
```bash
cat /etc/shells
```

Change your Shell:
```bash
sudo chsh -s /bin/zsh root
```
Create config:
```bash
vim ~/.zshrc
```

Add to .zshrc
```bash
#### ----------------------------------------
#### ~/.zshrc — Universal for normal user and root
#### ----------------------------------------

#### -------------------------------
#### Homebrew (Apple Silicon)
#### -------------------------------

[[ -x /opt/homebrew/bin/brew ]] && eval "$(/opt/homebrew/bin/brew shellenv)"

# Optional: coreutils (GNU tools)
# Uncomment if you want GNU coreutils aliases like `ls` → `gls`
# export PATH="/opt/homebrew/opt/coreutils/libexec/gnubin:$PATH"

#### -------------------------------
#### Update Homebrew Weekly
#### -------------------------------

# Only run brew update if > 7 days old
if [[ ! -f ~/.last_brew_update ]] || (( $(date +%s) - $(<~/.last_brew_update) > 604800 )); then
    brew update >/dev/null
    date +%s > ~/.last_brew_update
fi

#### -------------------------------
#### PATH Updates
#### -------------------------------

# LM Studio CLI
[[ ":$PATH:" != *":/Users/rj/.lmstudio/bin:"* ]] && export PATH="/Users/rj/.lmstudio/bin:$PATH"

# Docker Desktop CLI completions
fpath=(/Users/rj/.docker/completions $fpath)

#### -------------------------------
#### Autocompletion with Cache
#### -------------------------------

ZSH_COMPDUMP_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/zsh"
mkdir -p "$ZSH_COMPDUMP_DIR"
autoload -Uz compinit colors
colors
compinit -d "${ZSH_COMPDUMP_DIR}/zcompdump"

#### -------------------------------
#### Prompt symbols & colors
#### -------------------------------

APPLE_NORMAL="🍏"
APPLE_ROOT="🍎"
COLOR_NORMAL="%F{green}"
COLOR_INFO="%F{blue}"
COLOR_ROOT="%F{red}"
COLOR_WHITE="%F{white}"

# Prompt
if [[ "$EUID" -eq 0 ]]; then
  PROMPT="${COLOR_ROOT}┌─${COLOR_WHITE}%n${APPLE_ROOT}%m${COLOR_ROOT} [%~]%f
${COLOR_ROOT}└─${COLOR_WHITE}# %f"
else
  PROMPT="${COLOR_NORMAL}┌─${COLOR_INFO}%n${APPLE_NORMAL}%m${COLOR_NORMAL} [%~]%f
${COLOR_NORMAL}└─${COLOR_INFO}$ %f"
fi

# Right-side prompt (current time)
RPROMPT="%F{yellow}%*%f"

# Show last exit code in prompt if non-zero
precmd() {
  if [[ $? -ne 0 ]]; then
    echo -n "%F{red}[exit $?]%f "
  fi
  print -Pn "\e]0;%n@%m: %~\a"
}

#### -------------------------------
#### Shell Behavior & Safety
#### -------------------------------

setopt APPEND_HISTORY
setopt SHARE_HISTORY
setopt INC_APPEND_HISTORY
setopt HIST_IGNORE_DUPS
setopt HIST_REDUCE_BLANKS
setopt HIST_EXPIRE_DUPS_FIRST
setopt NO_NOMATCH
setopt NULL_GLOB
setopt NO_BEEP
setopt EXTENDED_GLOB
setopt NO_CASE_GLOB
setopt INTERACTIVE_COMMENTS

# Safer scripts
set -o pipefail

#### -------------------------------
#### History
#### -------------------------------

export XDG_CACHE_HOME="$HOME/.cache"
HISTFILE="$XDG_CACHE_HOME/zsh/history"
HISTSIZE=5000
SAVEHIST=5000

#### -------------------------------
#### Aliases
#### -------------------------------

# Safer file operations
alias rm='rm -i'
alias cp='cp -i'
alias mv='mv -i'

# Colorful and detailed ls
alias ls='ls -G'
alias ll='ls -lah --color=auto 2>/dev/null || ls -lahG'
alias la='ls -laG'
alias l='ls -lG'
alias lt='ls -ltrhG'

# Navigation
alias ..='cd ..'
alias ...='cd ../..'

# Other handy aliases
alias grep='grep --color=auto'
alias egrep='grep -E --color=auto'
alias fgrep='grep -F --color=auto'
alias diff='diff --color=auto'
alias c='clear'
alias myip='curl -s checkip.amazonaws.com'
alias ports='command lsof -i -P -n | grep LISTEN'
alias py='python3'
alias ipy='ipython3'
alias pip='pip3'
alias path='print -l $path'
alias q='exit'
alias mkd='mkdir -p'
alias please='sudo'
alias g='git'
alias v='vim'
alias h='history'
alias u='brew update && brew upgrade && brew cleanup'
alias cc='sync && sudo purge && clear'
alias brewdoctor='HOMEBREW_NO_ENV_HINTS=1 brew doctor'

#### -------------------------------
#### Editor & Pager
#### -------------------------------

export EDITOR=vim
export VISUAL=vim
export PAGER=less

#### -------------------------------
#### Less colors for man pages
#### -------------------------------

export LESS_TERMCAP_mb=$'\e[1;31m'
export LESS_TERMCAP_md=$'\e[1;36m'
export LESS_TERMCAP_me=$'\e[0m'
export LESS_TERMCAP_so=$'\e[01;33m'
export LESS_TERMCAP_se=$'\e[0m'
export LESS_TERMCAP_us=$'\e[1;32m'
export LESS_TERMCAP_ue=$'\e[0m'

#### -------------------------------
#### Bindings
#### -------------------------------

bindkey '^R' history-incremental-search-backward

#### -------------------------------
#### Zsh Plugins
#### -------------------------------

# zsh-autosuggestions
if [ -f /opt/homebrew/share/zsh-autosuggestions/zsh-autosuggestions.zsh ]; then
  source /opt/homebrew/share/zsh-autosuggestions/zsh-autosuggestions.zsh
fi

# zsh-syntax-highlighting (must be last)
if [ -f /opt/homebrew/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ]; then
  source /opt/homebrew/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
fi

#### -------------------------------
#### Local Config (Optional)
#### -------------------------------

[[ -f ~/.zsh_aliases ]] && source ~/.zsh_aliases

#### -------------------------------
#### iTerm2 shell integration
#### -------------------------------

test -e "${HOME}/.iterm2_shell_integration.zsh" && source "${HOME}/.iterm2_shell_integration.zsh"

```

```bash
#### -------------------------------
#### Install commands for my zshrc
#### -------------------------------

# Install Homebrew (if not installed)
# Visit brew.sh for latest, or run:
#   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Update brew
brew update

# Zsh enhancements
brew install zsh
brew install zsh-syntax-highlighting
brew install zsh-autosuggestions

# GNU tools (optional, if you want gnubin path)
brew install coreutils

# iTerm2 integration script (optional if using iTerm2)
curl -L https://iterm2.com/shell_integration/zsh \
    -o ~/.iterm2_shell_integration.zsh

# Development & tools
brew install vim
brew install git
brew install ipython
brew install python
brew install lsof
brew install curl
brew install diffutils

# Nice-to-haves
brew install less
brew install grep
brew install gnu-sed
brew install wget

# LM Studio (optional, if you use it)
# Usually installed via their official site or installer
# but if there’s a CLI, ensure it’s in your PATH

#### -------------------------------
#### End install commands
#### -------------------------------

```