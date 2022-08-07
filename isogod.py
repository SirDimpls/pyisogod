import io, os, sys, subprocess, argparse, shutil
import time, random
from threading import Thread, Lock

#########################################
# TODOs:
#   - [x] PS1's "in-cold-blood-2-discs-u-slus-01294-and-slus-01314" has both disc 1 and 2 as mds/mdf, double trouble:
#   - [x] implement mds/mdf support: mymdf2iso converts mdf to iso, then PSXCueMaker-Release-Win32-64bit.exe generates cue?
#   - [ ] handle multiple game discs in one package somehow, assume they are all in the same work folder and need to number them too
#   - [ ] implement lone mdf support: just mymdf2iso it
#   - [ ] implement lone bin support: use PSXCueMaker to generate cue file
#   - [ ] NRG? https://archlinux.org/packages/community/x86_64/nrg2iso/ -> doesn't do mixed CDs and PS1 cds are
#   - [ ] debug myccd2cue and fix problem converting complex ccd in "extract/complex.ccd"
#   - [ ] CDI !? how the fuck do I convert that
#########################################

# Globals

PATH="."
THREADS=1
OUTPATH="chdout"
TEMPPATH="extract"
TOOLSPATH="tools"
TOOLS={
  "zip": "7z.exe",
  "unrar": "unrar.exe",
  "7z": "7z.exe",
  "chdman": "chdman.exe",
  "unecm": "unecm.exe",
  "ccd2cue": "myccd2cue.exe",
  "mdf2iso": "mymdf2iso.exe",
  "PSXCueMaker": "PSXCueMaker.exe",
  "sounder": "sounder.exe"
}

# System commands

def cmd_ls(path):
  return os.listdir(path)

def cmd_ls_files(path):
  fds = cmd_ls(path)
  fs = []
  for f in fds:
    if not os.path.isdir(os.path.join(path, f)):
      fs.append(f)
  return fs

def cmd_mkdir(path):
  try:
    os.mkdir(path)
  except FileExistsError as e:
    # Already exists, nothing to do
    pass

def cmd_run(args):
  print("CMD_RUN: " + str(args))
  return subprocess.run(args, capture_output=False, shell=False, check=True, stdout=subprocess.DEVNULL)

def cmd_run_shell(args):
  return subprocess.run(args, check=True)

def cmd_rm(filepath):
  if os.path.exists(filepath):
    os.remove(filepath)

def cmd_rmdir(path):
  if os.path.exists(path) and os.path.isdir(path):
    attempts = 5
    while attempts > 0:
      try:
        attempts -= 1
        shutil.rmtree(path)
        break
      except PermissionError as e:
        if attempts <= 0:
          print("cmd_rmdir failed with PermissionError, Windows locked the path probably: " + str(path))

# Enums

# PACK type
PACK_ZIP="zip"
PACK_7Z="7z"
PACK_RAR="rar"

# PROCESS phase of rompac
PROCESS_PRE="pre"
PROCESS_ASSIGNED="assigned"
PROCESS_PACK_EXTRACTED="extracted"
PROCESS_CHD_CREATED="chded"
PROCESS_TEMPS_CLEANED="cleaned"
PROCESS_COMPLETE="complete"
PROCESS_FAILED="failed"

# FORMAT is for supported image formats
FORMAT_UNKNOWN="unknown"
FORMAT_CUEBIN="cue/bin"
FORMAT_CUEIMG="cue/img"
FORMAT_CUEISO="cue/iso"
FORMAT_ISO="iso"
FORMAT_CCDIMG="ccd/img"
FORMAT_IMG="img"
FORMAT_MDSMDF="mds/mdf"
FORMAT_NRG="nrg"

# Utilities

# string.endwith() but lowers string case first
def util_endswith(name, ext):
  return name.lower().endswith(ext)

def get_pack_type(packpath):
  if util_endswith(packpath, "zip"):
    return "zip"
  elif util_endswith(packpath, "rar"):
    return "rar"
  elif util_endswith(packpath, "7z"):
    return "7z"
  else:
    return ""

def util_extract(packtype, packpath, temppath):
  args = []
  pp = packpath
  tp = temppath
  args = [os.path.join(TOOLSPATH, TOOLS["zip"]), "x", pp, "-o" + tp]
  return cmd_run(args)

def util_unecm(rompath, romfile):
  if not util_endswith(romfile, "ecm"):
    return False
  args = [os.path.join(TOOLSPATH, TOOLS["unecm"]), os.path.join(rompath, romfile), os.path.join(rompath, romfile[:-4])]
  res = cmd_run(args)
  return res.returncode == 0

def util_get_file_by_extension(path, ext):
  files = cmd_ls(path)
  found = None
  for f in files:
    if util_endswith(f, ext):
      found = f
      break
  return found

# Same as util_get_file_by_extension, but checks against a list of extensions
def util_get_file_by_extensions(path, ext_list):
  files = cmd_ls(path)
  found = None
  for f in files:
    if f[-3:].lower() in ext_list:
      found = f
      break
  return found

def util_chdman_createcd(rompath, cue_file, outpath, chd_name):
  args = [os.path.join(TOOLSPATH, TOOLS["chdman"]), "createcd", "--force", "--input", os.path.join(rompath, cue_file), "--output", os.path.join(outpath, chd_name + ".chd")]
  res = cmd_run(args)
  return res.returncode == 0

def util_ccd2cue(rompath, ccd_file, img_file):
  cue_file = img_file[:-3] + "cue"
  args = [os.path.join(TOOLSPATH, TOOLS["ccd2cue"]), "--input", os.path.join(rompath, ccd_file), "--output",
          os.path.join(rompath, cue_file), "--image", img_file]
  res = cmd_run(args)
  if res.returncode == 0:
    return cue_file
  else:
    return ""

# Becareful, this call causes cue file to have rompath+bin_file instead of just bin_file so requires a follow up step to correct
def util_mdf2cuebin(rompath, mdf_file):
  cue_file = mdf_file[:-3] + "cue"
  args = [os.path.join(TOOLSPATH, TOOLS["mdf2iso"]), "--cue", os.path.join(rompath, mdf_file)]
  res = cmd_run(args)
  if res.returncode == 0:
    return cue_file
  else:
    return ""

def util_mdf2iso(rompath, mdf_file):
  iso_file = mdf_file[:-3] + "iso"
  args = [os.path.join(TOOLSPATH, TOOLS["mdf2iso"]), os.path.join(rompath, mdf_file)]
  res = cmd_run(args)
  if res.returncode == 0:
    return iso_file
  else:
    return ""

def util_generate_cue_from_bin(rompath, bin_file):
  cue_file = bin_file[:-3] + "cue"
  args = [os.path.join(TOOLSPATH, TOOLS["PSXCueMaker"]), "--path", os.path.join(rompath, bin_file), "--output", cue_file]
  res = cmd_run(args)
  if res.returncode == 0:
    return cue_file
  else:
    return ""

def util_play_sound(soundfile):
  if soundfile and len(soundfile) > 0 and os.path.exists(soundfile):
    try:
      args = [os.path.join(TOOLSPATH, TOOLS["sounder"]), soundfile]
      cmd_run(args)
    except subprocess.CalledProcessError:
      pass
    return True

def util_correct_cue_image(rompath, cuefile, imagefile):
  low_imagefile = imagefile.lower()
  if not low_imagefile.endswith("bin") and not low_imagefile.endswith("img"):
    print("util_correct_cue_image called with non bin/img imagefile: " + str(imagefile))
    return False
  cf = open(os.path.join(rompath, cuefile), 'r')
  lines = cf.readlines()
  cf.close()
  for i in range(0, len(lines)):
    line = lines[i]
    l = line.lower()
    if l.startswith("file"):
      si = l.find("\"")
      ei = l.find("\"", si + 1)
      if si > -1 and ei > -1:
        filename = l[si + 1:ei]
        filename_raw = line[si + 1:ei]
        if filename_raw != imagefile and filename.endswith("bin") or filename.endswith("img"):
          print("FILENAME = " + filename_raw)
          print("IMAGEFILE = " + imagefile)
          lines[i] = line.replace(filename_raw, imagefile)
          print("Conversion complete")
          modded_cue = "\n".join(lines)
          with open(os.path.join(rompath, cuefile), 'w') as wf:
            wf.write(modded_cue)
          return True
  return False

def util_check_cue(rompath, cue_file):
  if not cue_file.endswith("cue"):
    return False
  cf = open(os.path.join(rompath, cue_file), 'r')
  lines = cf.readlines()
  cf.close()
  if len(lines) < 3:
    return False
  return True

# Jobs Messenger

JOBSYSTEM_MSNGR=[]

# Writes a message from specified thread to the jobsystem messenger
def jobsystem_emit_msg(thread_id, lock, msg):
  lock.acquire()
  JOBSYSTEM_MSNGR.append("{0}: {1}".format(thread_id, msg))
  lock.release()

# Returns a clone of all messages in the jobsystem messenger
def jobsystem_get_msgs(lock):
  cloned=[]
  lock.acquire()
  cloned = [m for m in JOBSYSTEM_MSNGR]
  JOBSYSTEM_MSNGR.clear()
  lock.release()
  return cloned

# Objects

def collect_packages(path):
  zr = cmd_ls(path)
  packs = []
  for f in zr:
    pp = os.path.join(path, f)
    if get_pack_type(pp) != "":
      packs.append(PackedRom(path, f))
  return packs

class PackedRom:
  packfile = ""
  packtype = ""
  romname = ""
  phase = PROCESS_PRE
  failure = ""
  workpath = ""
  thread_id = -1
  thread_lock = None
  rompath = ""
  romformat = FORMAT_UNKNOWN
  romecm = False

  def __init__(self, path, file):
    self.packfile = file
    self.packpath = path
    self.packtype = get_pack_type(os.path.join(path, file))
    if self.packtype == "":
      raise Exception("PackedRom has unknown type: " + str(self.packfile))
    self.romname = self.packfile[0:-4]
    self.workpath = os.path.join(TEMPPATH, self.romname)

  def begin(self):
    self.emit_msg("Starting processing rompack " + self.romname)
    cmd_mkdir(self.workpath)
    return True, ""

  def uncompress(self):
    # Compression
    self.emit_msg("Decompressing {0}..".format(self.packfile))
    ppath = os.path.join(self.packpath, self.packfile)
    try:
      res = util_extract(self.packtype, ppath, self.workpath)
    except Exception as e:
      return self.emit_msg("Decompression threw an error: " + str(e))
    if res and res.returncode != 0:
      m = "Failed to decompress with returncode: " + str(res.returncode)
      return self.emit_msg(m)
    if len(cmd_ls(self.workpath)) == 0:
      return self.emit_msg("Decompression looks successful but no files: " + self.workpath)
    self.emit_msg("Decompression done.")
    self.phase = PROCESS_PACK_EXTRACTED
    # Identification
    # Start with base folder
    # - Handle case where there is a single folder, change workpath to that folder
    self.rompath = self.workpath
    files = cmd_ls(self.rompath)
    if len(files) == 1 and os.path.isdir(os.path.join(self.rompath, files[0])):
      self.rompath = os.path.join(self.rompath, files[0])
    self.romformat = self.identify_format(self.rompath)
    if self.romformat == FORMAT_UNKNOWN:
      return self.emit_msg("Unknown rom format here: {0}".format(self.workpath))
    self.emit_msg("Rom format identified as: " + self.romformat)
    return True, ""

  def identify_format(self, path):
    exts = []
    files = cmd_ls_files(path)
    for f in files:
      ff = f.lower()
      e = ff[-3:]
      exts.append(e)
      if e == "ecm":
        exts.append(ff[-7:-4])
    if "ecm" in exts:
      self.romecm = True
    if "cue" in exts and "bin" in exts:
      return FORMAT_CUEBIN
    elif "cue" in exts and "img" in exts:
      return FORMAT_CUEIMG
    elif "cue" in exts and "iso" in exts:
      return FORMAT_CUEISO
    elif "iso" in exts:
      return FORMAT_ISO
    elif "ccd" in exts and "img" in exts:
      return FORMAT_CCDIMG
    elif "img" in exts:
      return FORMAT_IMG
    elif "mds" in exts and "mdf" in exts:
      return FORMAT_MDSMDF
    elif "nrg" in exts:
      return FORMAT_NRG
    else:
      print("UNKNOWN FORMAT! Extensions: " + str(exts))
      return FORMAT_UNKNOWN

  def unecm(self):
    if self.romecm:
      files = cmd_ls_files(self.rompath)
      for f in files:
        ff = f.lower()
        if ff[-3:] == "ecm":
          res = util_unecm(self.rompath, f)
          if res:
            # delete ecm file, no point in wasting space
            cmd_rm(os.path.join(self.rompath, f))
            print("UNECMed {0} successfully".format(f))
          else:
            return self.emit_msg("Failed to unecm {0}".format(f))
    return True, ""

  def convert(self):
    res = False
    if self.romformat == FORMAT_CUEBIN or self.romformat == FORMAT_CUEIMG or self.romformat == FORMAT_CUEISO:
      # CUE/BIN|IMG|ISO -> direct conversion to chd
      cue_file = util_get_file_by_extension(self.rompath, "cue")
      if cue_file == None:
        return self.emit_msg("Failed to retrive cue file despite format being detected as cue: " + self.rompath)
      # attempt to detect situation when CUE file refers to image using a full windows path in someone's computer
      img_file = util_get_file_by_extensions(self.rompath, ["bin", "img", "iso"])
      res = util_correct_cue_image(self.rompath, cue_file, img_file)
      if res:
        self.emit_msg("CUE wrong image and path were found and corrected: " + cue_file)
      res = util_chdman_createcd(self.rompath, cue_file, OUTPATH, self.romname)
      
    elif self.romformat == FORMAT_ISO:
      # ISO -> direct convert to chd
      iso_file = util_get_file_by_extension(self.rompath, "iso")
      if iso_file == None:
        return self.emit_msg("Failed to retrieve iso file despite format being detected as iso: " + self.rompath)
      res = util_chdman_createcd(self.rompath, iso_file, OUTPATH, self.romname)
      
    elif self.romformat == FORMAT_CCDIMG:
      # CCD/IMG -> convert CCD to CUE then CUE/IMG to chd
      ccd_file = util_get_file_by_extension(self.rompath, "ccd")
      if ccd_file == None:
        return self.emit_msg("Failed to retrieve ccd file despite format being detected as ccd/img: " + self.rompath)
      img_file = util_get_file_by_extension(self.rompath, "img")
      if img_file == None:
        return self.emit_msg("Failed to retrieve img file despite format being detected as ccd/img: " + self.rompath)
      cue_file = util_ccd2cue(self.rompath, ccd_file, img_file)
      if cue_file == "" or cue_file == None:
        return self.emit_msg("Failed to convert ccd to cue: " + self.rompath)
      if util_check_cue(self.rompath, cue_file) == False:
        return self.emit_msg("CCD to CUE conversion finished but failed as CUE file is less than 3 lines long: " + self.rompath)
      self.emit_msg("Conversion from CCD to CUE succesful: " + cue_file)
      res = util_chdman_createcd(self.rompath, cue_file, OUTPATH, self.romname)

    elif self.romformat == FORMAT_MDSMDF:
      # MDS/MDF -> convert MDF to CUE/BIN then re-generate CUE file then to chd
      mdf_file = util_get_file_by_extension(self.rompath, "mdf")
      if mdf_file == None:
        return self.emit_msg("Failed to retrieve mdf file despite format being detected as {0}: {1}"
                             .format(self.romformat, self.rompath))
      iso_file = util_mdf2iso(self.rompath, mdf_file)
      if iso_file == "":
        return self.emit_msg("Failed to generate ISO from MDF file: {0}".format(self.rompath))
      self.emit_msg("Generating ISO from MDF successful: " + iso_file)
      res = util_chdman_createcd(self.rompath, iso_file, OUTPATH, self.romname)
      
    elif self.romformat == FORMAT_IMG or self.romformat == FORMAT_NRG:
      # Yet to be implemented formats
      return self.emit_msg("Format not implemented yet: " + self.romformat)
    
    if not res:
      return self.emit_msg("Failed to convert to CHD: " + self.romname)
    self.phase = PROCESS_CHD_CREATED
    return True, ""

  def cleanup(self):
    cmd_rmdir(self.workpath)
    self.phase = PROCESS_TEMPS_CLEANED
    return True, ""

  def emit_msg(self, msg):
    if self.thread_id != -1 and self.thread_lock != None:
      jobsystem_emit_msg(self.thread_id, self.thread_lock, msg)
    return False, msg

# Jobs

def process_rompack(thread_id, lock, rompack):
  jobsystem_emit_msg(thread_id, lock, "Begin processing of " + rompack.romname)
  rompack.thread_id = thread_id
  rompack.thread_lock = lock

  rompack.begin()

  res, err = rompack.uncompress()
  if res:
    res, err = rompack.unecm()
    if res:
      res, err = rompack.convert()
      if res:
        res, err = rompack.cleanup()
        if res:
          rompack.phase = PROCESS_COMPLETE
        else:
          m = "Error during cleanup " + rompack.packfile + ": " + str(err)
          jobsystem_emit_msg(thread_id, lock, m)
          rompack.phase = PROCESS_FAILED
          rompack.failure = m
      else:
        m = "Error during conversion " + rompack.packfile + ": " + str(err)
        jobsystem_emit_msg(thread_id, lock, m)
        rompack.phase = PROCESS_FAILED
        rompack.failure = m
    else:
      m = "Error during unecm " + rompack.packfile + ": " + str(err)
      jobsystem_emit_msg(thread_id, lock, m)
      rompack.phase = PROCESS_FAILED
      rompack.failure = m
  else:
    m = "Error during uncompressing " + rompack.packfile + ": " + str(err)
    jobsystem_emit_msg(thread_id, lock, m)
    rompack.phase = PROCESS_FAILED
    rompack.failure = m
  jobsystem_emit_msg(thread_id, lock, "Completed processing of " + rompack.romname)

class JobSystem:
  threads = []
  def __init__(self):
    for i in range(0, THREADS):
      self.threads.append(None)

  # returns an available thread slot or -1 if none
  def get_next_slot(self):
    for i in range(0, len(self.threads)):
      if self.threads[i] == None:
        return i
    return -1

  # return true if any thread is free
  def has_available_thread(self):
      return self.get_next_slot() != -1

  # returns number of free threads
  def count_free_threads(self):
    at = 0
    for i in range(0, len(self.threads)):
      if self.threads[i] == None:
        at += 1
    return at

  def start_system(self, rompacks):
    lock = Lock()
    try:
      while True:
        remaining_packs=0
        # Starting threads to process rompacks
        for r in rompacks:
          if r.phase == PROCESS_PRE:
            remaining_packs += 1
            ntid = self.get_next_slot()
            if ntid > -1:
              self.threads[ntid] = Thread(target=process_rompack, args=(ntid, lock, r))
              r.phase = PROCESS_ASSIGNED
              print("JobSystem: beginning processing rompack {0} on thread {1}..".format(r.romname, str(ntid)))
              self.threads[ntid].start()
        
        # Threads management
        for i in range(0, len(self.threads)):
          if remaining_packs > 0:
            if self.threads[i] != None:
              if self.threads[i].is_alive():
                # Thread is processing
                pass
              else:
                # Thread is done so clear
                print("JobSystem: finished process on thread {0}".format(i))
                self.threads[i] = None
          else:
            # all packs have been processed or are being processed
            self.threads[i].join()
            self.threads[i] = None
        if remaining_packs == 0:
          if self.count_free_threads() == THREADS:
            break
          else:
            print("JobSystem arrived at no remaining packs, assumes all threads terminated, but there are remaining non-free threads?")

        msngr = jobsystem_get_msgs(lock)
        for m in msngr:
          print("THREAD " + str(m))
        
        time.sleep(1)
    except Exception as e:
      print("Exception thrown while jobsystem is running")
      print(e)
      

# Main

if __name__=="__main__":
  print("PS1 GOD: super PS1/DC packed images converter to chd")

  parser = argparse.ArgumentParser(description='Scan and convert all packaged PS1/DC roms to CHDs')
  parser.add_argument("--path", default=".", help='path where packed roms are')
  parser.add_argument("--temp", default="extract", help='path for temporary extracted files and folders for all processing threads')
  parser.add_argument("--output", default="chdout", help='path where to place the CHD roms')
  parser.add_argument("--delete", type=bool, default=False, help='DANGEROUS! delete source pack if CHD conversion is successful')
  parser.add_argument("--threads", type=int, default=1, help='how many worker threads to use? fast on SSDs, slow on HDDs')

  args = parser.parse_args()
  if len(args.path) > 0:
    PATH = args.path
  if len(args.output) > 0:
    OUTPATH = args.output
    cmd_mkdir(OUTPATH)
  if len(args.temp) > 0:
    TEMPPATH = args.temp
  THREADS = args.threads
  if THREADS < 1:
    THREADS = 1

  print("Target path = " + PATH)
  print("Threads = " + str(THREADS))
  print("Temp path = " + TEMPPATH)
  print("Output path = " + OUTPATH)
  
  packs = collect_packages(PATH)
  if len(packs) == 0:
    print("NO COMPATIBLE PACKS FOUND (zip, rar, 7z) DID YOU FORGET TO SPECIFY --path?\n")
    parser.print_help()
    exit(1)

  # make sure TEMPPATH is not empty
  cmd_mkdir(TEMPPATH)
  if len(cmd_ls(TEMPPATH)) > 0:
    print("TEMP Path is not empty! ({0}) this script isn't written to handle half-way through conversions".format(TEMPPATH))
    exit(1)
  
  print()
  i = 0
  for f in packs:
    print("{0}: {1}".format(i, f.packfile))
    i += 1

  print("START PROCESSING {0} ROM PACKS".format(len(packs)))
  jobs = JobSystem()
  jobs.start_system(packs)

  print("\nProcessed {0} roms across {1} threads.".format(len(packs), THREADS))
  print("\nSuccessful:")
  for f in packs:
    if f.phase == PROCESS_COMPLETE:
      print("  {0} ({1})".format(f.romname, f.romformat))
  print("\nFailed:")
  fcount = 0
  for f in packs:
    if f.phase == PROCESS_FAILED:
      print("  {0} ({1}): {2}".format(f.romname, f.romformat, f.failure))
      fcount += 1
  if fcount == 0:
    print("  None")
  print("\nAnomalies:")
  acount = 0
  for f in packs:
    if f.phase != PROCESS_COMPLETE and f.phase != PROCESS_FAILED:
      print("  {0} ({1}): failed after '{2}'".format(f.romname, f.romformat, f.phase))
      acount += 1
  if acount == 0:
    print("  None")
  print("\nCOMPLETE")
  util_play_sound("tools/assets/COMPLETE.WAV")
