#!/usr/bin/env bats

setup() {
  load '../test_helper/bats-support/load'
  load '../test_helper/bats-assert/load'

  # get the containing directory of this file
  # use $BATS_TEST_FILENAME instead of ${BASH_SOURCE[0]} or $0,
  # as those will point to the bats executable's location or the preprocessed file respectively
  DIR="$( cd "$( dirname "$BATS_TEST_FILENAME" )" >/dev/null 2>&1 && pwd )"
  # make executables in src/ visible to PATH
  PATH="$DIR/../../shell/bin:$PATH"
}

@test "Rename file with space" {
  run rename_media.sh '01/MASH S01E01 - The Pilot.mkv'
  assert_output 'mv.sh "01/MASH S01E01 - The Pilot.mkv" "01/MASH-01x01-The_pilot.mkv"'
}

@test "Rename file with dots" {
  run rename_media.sh '01/MASH S01E01 My.Long.Title.mkv'
  assert_output 'mv.sh "01/MASH S01E01 My.Long.Title.mkv" "01/MASH-01x01-My_long_title.mkv"'
}

@test "Rename file with suspension dots" {
  run rename_media.sh 'MASH/01/MASH S01E18 - Dear Dad...Again.mkv'
  assert_output 'mv.sh "MASH/01/MASH S01E18 - Dear Dad...Again.mkv" "MASH/01/MASH-01x18-Dear_dad...again.mkv"'
}

@test "Rename file with abbreviation" {
  run rename_media.sh '01/MASH S01E22 - Major Fred C. Dobbs.mkv'
  assert_output 'mv.sh "01/MASH S01E22 - Major Fred C. Dobbs.mkv" "01/MASH-01x22-Major_fred_c.Dobbs.mkv"'
}

@test "Rename file with multiple abbreviation" {
  run rename_media.sh 'MASH/02/MASH S02E07 - L.I.P. (Local Indigenous Personnel).mkv'
  assert_output 'mv.sh "MASH/02/MASH S02E07 - L.I.P. (Local Indigenous Personnel).mkv" "MASH/02/MASH-02x07-L.I.P.(Local_indigenous_personnel).mkv"'
}
