 import os
  import re
  import shutil

  # Configuration
  DESKTOP_DIR = r"C:\Users\msimmons\OneDrive - The Restored Church of God\Desktop\Greatest Untold Story"
  ARCHIVES_DIR = r"S:\3. Church Documents\05 - Sermon Transcripts\Archives"

  def extract_part_number(filename):
      """Extract part number from filename"""
      patterns = [
          r'\(Part\s+(\d+)\)',  # (Part 123)
          r'Part\s+(\d+)',       # Part 123
          r'Part_(\d+)',         # Part_123
      ]

      for pattern in patterns:
          match = re.search(pattern, filename, re.IGNORECASE)
          if match:
              return int(match.group(1))
      return None

  def scan_directory(directory):
      """Scan directory and return dict of {part_number: filename}"""
      parts = {}
      if not os.path.exists(directory):
          print(f"WARNING: Directory not found: {directory}")
          return parts

      for filename in os.listdir(directory):
          if filename.endswith(('.docx', '.pdf')) and not filename.startswith('~$'):
              part_num = extract_part_number(filename)
              if part_num:
                  if part_num in parts:
                      print(f"  Duplicate Part {part_num}: {filename}")
                  parts[part_num] = filename

      return parts

  def main():
      print("=" * 70)
      print("FINDING MISSING PARTS")
      print("=" * 70)

      # Scan Desktop folder
      print(f"\n1. Scanning Desktop folder...")
      desktop_parts = scan_directory(DESKTOP_DIR)
      print(f"   Found {len(desktop_parts)} parts")

      # Scan Archives folder
      print(f"\n2. Scanning Archives folder...")
      archives_parts = scan_directory(ARCHIVES_DIR)
      print(f"   Found {len(archives_parts)} parts")

      # Find missing parts
      print(f"\n3. Finding missing parts...")
      missing_part_numbers = set(archives_parts.keys()) - set(desktop_parts.keys())
      missing_part_numbers = sorted(missing_part_numbers)

      if not missing_part_numbers:
          print("   ✓ No missing parts!")
          return

      print(f"   Found {len(missing_part_numbers)} missing parts!")
      print(f"\n   Missing: {missing_part_numbers[:20]}")
      if len(missing_part_numbers) > 20:
          print(f"   ... and {len(missing_part_numbers) - 20} more")

      # Ask for confirmation
      print(f"\n4. Ready to copy {len(missing_part_numbers)} files")
      response = input("\n   Proceed? (yes/no): ").strip().lower()

      if response not in ['yes', 'y']:
          print("   Cancelled.")
          return

      # Copy files
      print(f"\n5. Copying files...")
      copied = 0
      errors = 0

      for part_num in missing_part_numbers:
          filename = archives_parts[part_num]
          src = os.path.join(ARCHIVES_DIR, filename)
          dst = os.path.join(DESKTOP_DIR, filename)

          try:
              shutil.copy2(src, dst)
              copied += 1
              print(f"   ✓ Part {part_num}")
          except Exception as e:
              errors += 1
              print(f"   ✗ ERROR Part {part_num}: {e}")

      # Summary
      print("\n" + "=" * 70)
      print(f"Copied: {copied} | Errors: {errors}")
      print(f"Total in Desktop: {len(desktop_parts) + copied}")
      print("=" * 70)

  if __name__ == "__main__":
      main()