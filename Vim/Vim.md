# VIM
---

Create config
```bash
vim ~/.vimrc
```
Paste into ~/.vimrc
```bash
" Enable syntax highlighting
syntax on

" Use dark background
set background=dark

" True color support
if has("termguicolors")
  set termguicolors
endif

" Colorscheme
colorscheme onedark

" Force pure black background
highlight Normal guibg=#000000 ctermbg=NONE
highlight NonText guibg=#000000
highlight NormalNC guibg=#000000
highlight CursorLine guibg=#1c1c1c

" Editor settings
set number                  " Show absolute line numbers
" set relativenumber
set cursorline
set ignorecase
set smartcase
set incsearch
set hlsearch
set tabstop=4
set shiftwidth=4
set expandtab
set autoindent
set smartindent
set laststatus=2
set ruler
set mouse=a
set backspace=indent,eol,start
set clipboard=unnamedplus
set showmatch
" set colorcolumn=80
highlight ColorColumn ctermbg=0 guibg=#1c1c1c
set lazyredraw
set scrolloff=5
set sidescrolloff=5

" No swap files (optional)
" set noswapfile
" set nobackup
" set nowritebackup

" Whitespace
set list
set listchars=tab:→\ ,trail:·

" Bindings
inoremap jk <Esc>
nmap <C-s> :w<CR>
imap <C-s> <Esc>:w<CR>i
nnoremap <Leader><space> :nohlsearch<CR>
nnoremap <Leader>sp :set spell!<CR>

" Statusline
set statusline=%F\ %y\ %m\ %r\ %=L:%l/%L\ C:%c

" Folding
set foldmethod=syntax
set foldlevel=99
```