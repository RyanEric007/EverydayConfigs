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
#### =========================================================
#### Universal ~/.zshrc — macOS User + Root Safe (FINAL)
#### =========================================================

##### Detect root vs user
if [[ "$EUID" -eq 0 ]]; then
  IS_ROOT=1
else
  IS_ROOT=0
fi

##### =========================================================
##### PATH — MUST BE FIRST
##### =========================================================
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Enable python + pip unversioned commands (python, pip)
if [[ $IS_ROOT -eq 0 ]]; then
  export PATH="/opt/homebrew/opt/python@3.14/libexec/bin:$PATH"
fi

# Load Homebrew env (user only)
if [[ $IS_ROOT -eq 0 ]] && [[ -x /opt/homebrew/bin/brew ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi

##### =========================================================
##### ZSH cache + completion
##### =========================================================
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
mkdir -p "$XDG_CACHE_HOME/zsh"

autoload -Uz compinit colors
colors
compinit -d "$XDG_CACHE_HOME/zsh/zcompdump"

##### =========================================================
##### Prompt (root vs user)
##### =========================================================
APPLE_NORMAL="🍏"
APPLE_ROOT="🍎"
COLOR_NORMAL="%F{green}"
COLOR_INFO="%F{blue}"
COLOR_ROOT="%F{red}"
COLOR_WHITE="%F{white}"

if [[ $IS_ROOT -eq 1 ]]; then
  PROMPT="${COLOR_ROOT}┌─${COLOR_WHITE}%n${APPLE_ROOT}%m${COLOR_ROOT} [%~]%f
${COLOR_ROOT}└─${COLOR_WHITE}# %f"
else
  PROMPT="${COLOR_NORMAL}┌─${COLOR_INFO}%n${APPLE_NORMAL}%m${COLOR_NORMAL} [%~]%f
${COLOR_NORMAL}└─${COLOR_INFO}$ %f"
fi

RPROMPT="%F{yellow}%*%f"

precmd() {
  if [[ $? -ne 0 ]]; then
    echo -n "%F{red}[exit $?]%f "
  fi
  print -Pn "\e]0;%n@%m: %~\a"
}

##### =========================================================
##### Shell behavior
##### =========================================================
setopt APPEND_HISTORY SHARE_HISTORY INC_APPEND_HISTORY
setopt HIST_IGNORE_DUPS HIST_REDUCE_BLANKS HIST_EXPIRE_DUPS_FIRST
setopt NO_NOMATCH NULL_GLOB NO_BEEP EXTENDED_GLOB NO_CASE_GLOB
setopt INTERACTIVE_COMMENTS
set -o pipefail

HISTFILE="$XDG_CACHE_HOME/zsh/history"
HISTSIZE=5000
SAVEHIST=5000

##### =========================================================
##### Aliases safe for both accounts
##### =========================================================
alias ls='ls -G'
alias ll='ls -lahG'
alias la='ls -laG'
alias l='ls -lG'
alias lt='ls -ltrhG'
alias ..='cd ..'
alias ...='cd ../..'
alias grep='grep --color=auto'
alias diff='diff --color=auto'
alias rm='rm -i'
alias cp='cp -i'
alias mv='mv -i'
alias c='clear'
alias h='history'
alias q='exit'

##### =========================================================
##### USER ONLY SECTION (Homebrew, Python, plugins)
##### =========================================================
if [[ $IS_ROOT -eq 0 ]]; then

  # User paths AFTER brew
  export PATH="$HOME/.lmstudio/bin:$PATH"
  export PATH="$HOME/Library/Python/3.14/bin:$PATH"

  # Editors
  export EDITOR=vim
  export VISUAL=vim
  export PAGER=less

  # Python convenience
  alias python=python3
  alias pip=pip3
  alias py='python3'
  alias ipy='ipython3'

  # Networking helpers
  alias myip='curl -s checkip.amazonaws.com'
  alias lip='ipconfig getifaddr en0'
  alias ports='lsof -i -P -n | grep LISTEN'

  # Brew maintenance
  alias u='brew update && brew upgrade && brew cleanup'
  alias brewdoctor='HOMEBREW_NO_ENV_HINTS=1 brew doctor'

  # Docker completions
  [[ -d "$HOME/.docker/completions" ]] && fpath=("$HOME/.docker/completions" $fpath)

  # Zsh plugins
  [[ -f /opt/homebrew/share/zsh-autosuggestions/zsh-autosuggestions.zsh ]] && \
    source /opt/homebrew/share/zsh-autosuggestions/zsh-autosuggestions.zsh

  [[ -f /opt/homebrew/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ]] && \
    source /opt/homebrew/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh

fi
```

```
sudo cp ~/.zshrc /var/root/.zshrc
```