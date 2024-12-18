
import sys

def print_file(filename):
    try:
        with open(filename, 'r') as file:
            print(f"\n{'='*80}")
            print(f"File: {filename}")
            print('='*80)
            print(file.read())
            print('='*80 + '\n')
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found")
    except Exception as e:
        print(f"Error reading file: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python print_file.py <filename>")
    else:
        print_file(sys.argv[1])
