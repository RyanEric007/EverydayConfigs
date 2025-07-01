# Syntactic Sugar

## Bash CLI Sugar

### Semicolon `;`

You can execute multiple commands sequentially in a single line by separating them with a semicolon (`;`). Each command will run regardless of whether the previous one succeeds.

```bash
command1; command2; command3
```

---

### Ampersand `&&`

To run commands sequentially but stop if one fails, use `&&`. The next command will only execute if the previous one succeeds.

```bash
command1 && command2 && command3
```

---

### Vertical Bars `||`

To run a command only if the previous one fails, use `||`.

```bash
command1 || command2
```

---

### Combining Logic (`&&` and `||`)

You can combine these operators to create conditional flows.

```bash
command1 && command2 || command3
```

- If `command1` succeeds, `command2` runs.
- If `command1` fails, `command3` runs.

---

### Subshell / Group Commands (`(...)` or `{ ...; }`)

If you want to group commands, you can use a subshell (`(...)`) or braces (`{ ...; }`).

**Subshell:** Runs all commands in a new shell environment.

```bash
(command1; command2; command3)
```

**Braces:** Runs all commands in the same shell.

```bash
{ command1; command2; command3; }
```

---

### Command Substitution (`$(...)` or Backticks)

Use `$(...)` instead of backticks (`` `command` ``) for embedding commands in another. It’s clearer and less error-prone.

**Use:**

```bash
echo "Today is $(date)"
```

**Instead of:**

```bash
echo "Today is `date`"
```

---

### The `[[ ... ]]` for Conditional Tests

Use `[[ ... ]]` instead of `[ ... ]` for conditionals. It’s more versatile and supports advanced string operations and regex.

**Use:**

```bash
if [[ $var == "hello" ]]; then
  echo "Hi there!"
fi
```

**Instead of:**

```bash
if [ "$var" = "hello" ]; then
  echo "Hi there!"
fi
```

---

### Using `:-` for Default Values

Provide default values for variables with `:-`.

**Example:**

```bash
echo "${name:-Guest}"
```

---

### Arithmetic Expansion (`$((...))`)

Perform arithmetic directly within `((...))` or `$((...))`.

**Example:**

```bash
sum=$((5 + 3))
echo "Sum is $sum"
```

---

### Shorthand `if` Statements

Combine `if`, `then`, and `fi` into a single line using `&&` and `||`.

**Example:**

```bash
[ $var -eq 10 ] && echo "It's ten!" || echo "Not ten!"
```

---

### Using `: >` to Empty a File

Use `: > filename` instead of `> filename` to truncate a file.

**Example:**

```bash
: > logfile
```

---

### Brace Expansion `{}`

Generate patterns or sequences easily.

```bash
echo file_{1..3}.txt
# Output: file_1.txt file_2.txt file_3.txt
```

---

### Globbing (`*`, `?`, `[abc]`)

Use wildcards for flexible pattern matching.

```bash
ls *.txt           # Lists all .txt files
ls file?.txt       # Matches files like file1.txt, file2.txt
ls file[1-3].txt   # Matches file1.txt, file2.txt, file3.txt
```