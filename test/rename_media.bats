#!/usr/bin/env bats

setup() {
  load 'test_helper/bats-support/load'
  load 'test_helper/bats-assert/load'

  # get the containing directory of this file
  # use $BATS_TEST_FILENAME instead of ${BASH_SOURCE[0]} or $0,
  # as those will point to the bats executable's location or the preprocessed file respectively
  DIR="$( cd "$( dirname "$BATS_TEST_FILENAME" )" >/dev/null 2>&1 && pwd )"
  # make executables in src/ visible to PATH
  PATH="$DIR/../shell/bin:$PATH"
}

@test "Rename file with space" {
  run rename_media.sh '01/MASH S01E01 - The Pilot.mkv'
  assert_output 'mv.sh "01/MASH S01E01 - The Pilot.mkv" "01/MASH-01x01-The_pilot.mkv"'
}

@test "Rename file with dots" {
  run rename_media.sh '01/MASH S01E01 My.Long.Title.mkv'
  assert_output 'mv.sh "01/MASH S01E01 My.Long.Title.mkv" "01/MASH-01x01-My_long_title.mkv"'
}

@test "Rename file with abbreviation" {
  run rename_media.sh '01/MASH S01E22 - Major Fred C. Dobbs.mkv'
  assert_output 'mv.sh "01/MASH S01E22 - Major Fred C. Dobbs.mkv" "01/MASH-01x22-Major_fred_c.Dobbs.mkv"'
}
