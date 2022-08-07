# PyISOGod

Automate conversion of large ISO dumps to CHDs for PS1/DC meant for use for handheld gaming devices/MisterFPGA/etc

This is a **Python 3 Windows** script that runs in command line developed and tested in Windows only (I use [cmder](https://github.com/cmderdev/cmder) in Windows).
The script is paired with a number of windows binary tools found online (some modified).

There are many limits here but for about 95% of cases this should work. Some glaring limitations I haven't implemented due to complexity/limited value:

* NRG to CHD conversion: NRG is a closed format and the only tools I found that can convert them do not support mixed-mode images which PS1 games depend on.
* CDI to CHD conversion: also closed format, but this one has an additional challenge. A part of the image is compressed in some (all?) cases and it's a lossy compression so no good for preserving original games.
* Handling edge cases such as a single zip/7z/rar archive containing multiple disks or problematically named image files such as those starting with a space like " something.iso"

I tested this script on a PS1 dump and a Dreamcast dump from archive. Dreamcast dump was almost 100% successful as it was strictly using GDI correct image files (only failures were corrupt archives). PS1 was all over the place including a handful of NRG, CDI, and just strange file names or corrupt archives.

Resulting CHDs were tested in PC emulators and under [Adam system image emulators](https://github.com/eduardofilo/RG350_adam_image).

## Features

* supported formats/variants conversion to CHD: cue/bin, cue/img, cue/iso, iso, ccd/img, img, gdi
* for ccd/img, CCD will be converted to a CUE file however the conversion tool has trouble converting complex images (many tracks) so will only work for simpler images
* isogod can optionally run the conversion on multiple threads, this would probably take eternity on HDDs so should be run on SSDs only.
* isogod will detect anomalies and failures during conversions and report them at the end. Anomalies are unexpected failures in the middle of processing what looked like a valid image
* isogod will check validity of CUE image file and correct the path to remove any Windows hardcoded paths (surprisingly common in iso archive dumps)
 
When multi-threaded, if an exception is thrown and kills the main python thread, conversion of images in worker threads will continue and conclude uninterrupted. This shouldn't be common but I've seen it once.

## How to run

isogod requires 3 paths: a source path to read the compressed images from (rar/zip/7z), a temporary path to uncompress images to and process them in (failed images are left uncompressed there), and an output path to write the CHD files to.

For example if our archive of iso images is in: `D:\PS1\archive\`, our temp folder could be: `D:\PS1\temp`, and our output: `D:\PS1`, then this is isogod can be run:

```
python isogod.py --path "D:\PS1\archive" --temp "D:\PS1\temp" --output "D:\PS1"
```

You may also add a `--threads 4` to run 4 threads of conversion (or any number you want), just remember that this is only beneficial for SSDs and you probably should stay within the threads count of your CPU.

## Modified Tools

Here are the modified binary tools:

* [mymdf2iso](https://github.com/SirDimpls/mymdf2iso): modified to fix an issue that slowed this tool down significantly
* [psx_cue_maker_desktop](https://github.com/SirDimpls/psx_cue_maker_desktop): modified to support running it from command line
* [myccd2cue](https://github.com/SirDimpls/myccd2cue): quick and dirty port from Linux to Windows

## Blog

Inception and progress of this script [kinda documented in mastodon](https://pinafore.social/statuses/108564421678064517).
