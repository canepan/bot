#!/usr/bin/perl -w
#
# RETrieve_Machine_Temperature, retmt:
#  Retrieve the temperatures measured within the RPI3 machine and report
#  them to Xymon.
#
# Written by W.J.M. Nelis, wim.nelis@ziggo.nl, 2017.10
#
# Modified by W.J.M. Nelis, wim.nelis@ziggo.nl, 2018.07
# - Specify the device type in the RRD file name, in this case 'cpu'.
#
use strict ;
use Time::Piece ;			# Format time

#
# Installation constants.
# -----------------------
#
my $XyDisp= $ENV{XYMSRV} ;		# Name of monitor server
my $XySend= $ENV{XYMON} ;		# Monitor interface program
my $FmtDate= "%Y.%m.%d %H:%M:%S" ;	# Default date format
   $FmtDate= $ENV{XYMONDATEFORMAT} if exists $ENV{XYMONDATEFORMAT} ;
my $HostName= `hostname` ;		# 'Source' of this test
chomp $HostName ;
my $TestName= 'env' ;			# Test name
my $ThresholdYellow= 60 ;		# Warning threshold [C]
my $ThresholdRed   = 70 ;		# Error threshold [C]

my @ColourOf= ( 'red', 'yellow', 'clear', 'green' ) ;

my $CpuFil= '/sys/class/thermal/thermal_zone0/temp' ;
my $GpuCmd= '/usr/bin/vcgencmd measure_temp' ;

#
# Global variables.
# -----------------
#
my $Now= localtime ;			# Timestamp of tests
   $Now= $Now->strftime( $FmtDate ) ;
my $Colour=  3 ;			# Test status
my $Result= '' ;			# Message to sent to Xymon
my %Temp ;				# Temperature readings

my %ErrMsg ;				# Error messages
   $ErrMsg{$_}= []		foreach ( @ColourOf ) ;

#
# Issue a message to the logfile. As this script is run periodically by Xymon,
# StdOut will be redirected to the logfile.
#
sub LogMessage {
  my $Msg= shift ;
  my @Time= (localtime())[0..5] ;
  $Time[4]++ ;  $Time[5]+= 1900 ;
  chomp $Msg ;
  printf "%4d%02d%02d %02d%02d%02d %s\n", reverse(@Time), $Msg ;
}  # of LogMessage

sub max($$) { return $_[0] > $_[1] ? $_[0] : $_[1] ; }
sub min($$) { return $_[0] < $_[1] ? $_[0] : $_[1] ; }

#
# Function InformXymon sends the message, in global variable $Result, to
# the Xymon server. Any error messages in %ErrMsg are prepended to the message
# and the status (colour) of the message is adapted accordingly.
#
sub InformXymon() {
  my $ErrMsg= '' ;
  my $Clr ;				# Colour of one sub-test

  for ( my $i= 0 ; $i < @ColourOf ; $i++ ) {
    $Clr= $ColourOf[$i] ;
    next			unless @{$ErrMsg{$Clr}} ;
    $Colour= min( $Colour, $i ) ;
    $ErrMsg.= "&$Clr $_\n"	foreach ( @{$ErrMsg{$Clr}} ) ;
  }  # of foreach
  $ErrMsg.= "\n"		if $ErrMsg ;

  $Colour= $ColourOf[$Colour] ;
  $Result= "\"status $HostName.$TestName $Colour $Now\n" .
	   "<b>Temperature sensor readings</b>\n\n" .
	   "$ErrMsg$Result\"\n" ;
  `$XySend $XyDisp $Result` ;		# Inform Xymon

  $Result= '' ;				# Reset message parameters
  $Colour=  3 ;
  $ErrMsg{$_}= []		foreach ( @ColourOf ) ;
}  # of InformXymon

#
# Function ReadSensors retrieves the temperatures and their thresholds. The
# results are stored in hash %Temp. In case of an error, the result area
# will be empty.
#
sub ReadSensors() {
  my @Lines ;				# Content of one 'file'

  %Temp= () ;				# Clear result area
  unless ( defined open(FH,'<',$CpuFil) ) {
    push @{$ErrMsg{clear}}, "Cannot read CPU temperature from $CpuFil:\n" .
			    "  $!" ;
  } else {
    @Lines= <FH> ;			# Read entire file
    unless ( @Lines == 1  and  $Lines[0] =~ m/^(\d+)/ ) {
      push @{$ErrMsg{clear}}, "Cannot read CPU temperature from $CpuFil\n:" .
			      "  Unexpected input" ;
    } else {
      $Temp{CPU}{label}= 'CPU' ;
      $Temp{CPU}{input}= sprintf( '%.1f', $1/1000 ) ;
      $Temp{CPU}{max}  = $ThresholdYellow ;
      $Temp{CPU}{crit} = $ThresholdRed ;
    }  # of else
  }  # of else

  @Lines= `$GpuCmd` ;			# Retrieve information
  if ( @Lines == 0 ) {
    push @{$ErrMsg{clear}}, "Cannot read GPU temperature from \`$GpuCmd\`:\n" .
			    "  no data returned" ;
  } else {
    chomp $Lines[0] ;
    unless ( $Lines[0] =~ m/^temp=([\d\.]+).+C$/ ) {
      push @{$ErrMsg{clear}}, "Cannot read GPU temperature from \`$GpuCmd\`:\n" .
			      "  unexpected input : $Lines[0]" ;
    } else {
      $Temp{GPU}{label}= 'GPU' ;
      $Temp{GPU}{input}= $1 ;
      $Temp{GPU}{max}  = $ThresholdYellow ;
      $Temp{GPU}{crit} = $ThresholdRed ;
    }  # of else
  }  # of else
}  # of ReadSensors

#
# Function BuildMessage formats the collected data into a nice table, performs
# the threshold checks and leaves the results in the status indicator. The
# statistics are added in the DEVMON format to be moved into an RRD.
#
sub BuildMessage() {
  my ($TempMin,$TempAvg,$TempMax)= (100,0,-100) ;	# Temperature statistics
  my $T ;				# Ref to data of one sensor
  my $Clr ;				# Status (colour) of one reading

  if ( scalar(keys %Temp) == 0 ) {
    $Result= "No data received\n" ;
    return ;
  }  # of if

 #
 # Build a table showing the various sensors, their readings and their
 # thresholds.
 #
  $Result = "<table border=1 cellpadding=5>\n" ;
  $Result.= " <tr> <th>Sensor</th> <th>Temp [C]</th> <th>Threshold [C]</th> </tr>\n" ;
  foreach ( sort keys %Temp ) {
    $T= $Temp{$_} ;			# Ref to sensor data
    $Result.= " <tr> " ;
    $Result.= "<td>$$T{label}</td> " ;	# Name of sensor

    $TempMin= min( $TempMin, $$T{input} ) ;
    $TempMax= max( $TempMax, $$T{input} ) ;
    $TempAvg+= $$T{input} ;

    $Clr= 'green' ;			# Assume temperature in range
    if      ( $$T{input} < 10 ) {	# Temperature is too low
      $Clr= 'yellow' ;
      push @{$ErrMsg{$Clr}}, "Temperature of $$T{label} is low" ;
    } elsif ( $$T{input} >= $$T{crit} ) {
      $Clr= 'red' ;
      push @{$ErrMsg{$Clr}}, "Temperature of $$T{label} is too high" ;
    } elsif ( $$T{input} >= $$T{max}  ) {
      $Clr= 'yellow' ;
      push @{$ErrMsg{$Clr}}, "Temperature of $$T{label} is high" ;
    }  # of elsif

    $Result.= "<td align='right'>$$T{input} &$Clr</td> " ;
    $Result.= "<td align='right'>$$T{max}</td> " ;
    $Result.= "</tr>\n" ;
  }  # of foreach
  $Result.= "</table>\n" ;
  $TempAvg/= scalar( keys %Temp ) ;	# Average temperature
  $TempAvg = sprintf( '%5.1f', $TempAvg ) ;

 #
 # Append the statistics, using the DEVMON format.
 #
  $Result.= "<!-- linecount=1 -->\n" ;
  $Result.= "<!--DEVMON RRD: env 0 0\n" ;
  $Result.= "DS:Temperature:GAUGE:600:-100:100 DS:MinTemp:GAUGE:600:-100:100 DS:MaxTemp:GAUGE:600:-100:100\n" ;
  $Result.= "temp.cpu $TempAvg:$TempMin:$TempMax\n" ;
  $Result.= "-->" ;
}  # of BuildMessage


#
# ----- MAIN PROGRAM -----
#
ReadSensors ;
BuildMessage ;
InformXymon ;
