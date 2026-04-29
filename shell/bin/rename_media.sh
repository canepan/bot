#!/bin/bash
_dir_serie="${PWD}"
_serie="$(basename "${_dir_serie}")"

echo "${_serie}" | grep -Eq '^[0-9x]+$'
while [ $? -eq 0 ]; do
  _dir_serie="$(dirname "${_dir_serie}")"
  _serie="$(basename "${_dir_serie}")"
  echo "${_serie}" | grep -Eq '^[0-9x]+$'
done
if [ $# -lt 1 ]; then
  set *.avi *.mkv *.mp4
fi
#for i in ${@:-*.avi *.mkv *.mp4}; do
for i in "${@}"; do
#  echo mv.sh \"$i\" \"`echo $i | sed 's/^[^1-9]*\([1-9]*\)[Ex]/'${_serie}'-0\1x/ ; s/[-\. ]\(.\)/-\U\1/ ; s/[_\. ]\(.\)/_\L\1/g  ; s/_-_/-/g ; s/_iTA_dLMux_x264/-x264-ITA-DLMux/i ; s/_iTA_eNG_1080p_wEB-DLMux_h_*264/-h264-ITA_ENG-1080p-WED-DLMux/i ; s/_ita_web-dlmux_xvid/-XviD-ITA-WEB-DLMux/i ; s/_ita_web-dlmux_x264/-x264-ITA-WEB-DLMux/i ; s/_ita_eng_dlmux_xvid/-XviD-ITA_ENG/i ; s/S_o_s/S.o.s./i ; s/-ubi/-UBi/i ; s/_\[tutankemule_net\]//i ; s/novarip/NovaRip/i ; s/_hdtv_x264_sub_iTA_by_zF/-x264-ITA-HDTV-ZF/i ; s/_(720p_sub_ita)/-XviD-ENG_sub_ITA-720p/i ; s/_iTaEnG_bDmux/-ITA_ENG-BDMux/i ; s/.webrip/-WEBRip/i ; s/.xvid/-XviD/i ; s/.divx/-DivX/i ; s/[-_]avi$/.avi/i ; s/[-_]\([a-z][a-z]\)[-_]srt$/.\1.srt/i ; s/[-_]\(srt|mkv|avi|mp4\)$/.\1/i'`\"
  # more generic, 20191220
  echo mv.sh \""${i}"\" \"$(echo $i | sed '
    s/\([0-9]\) [eE][Pp][ \.]/\1x/ ;
    s/^[^1-9]*\([1-9]*\)[Ex]/'"${_serie}"'-0\1x/ ;
    s/ S\([0-9]*\)[-_\. E]\(.\)/-\1x\2/ ;
    s/[ _]-[ _]/-/g ;
    s/\([0-9]\)[-_\. ]\(.\)/\1-\U\2/ ;
    # s/\([a-zA-Z]\)\.\([a-zA-Z]\)/\1\x01\2/g ;
    s/\([a-zA-Z]\)\. /\1\x01/g ;
    s/\.\.\./\x02/g ;
    s/[_. ]\(.\)/_\L\1/g  ;
    s/\x02\(.\)/...\L\1/g ;
    s/\x01/./g ;
    s/\([^_]\)_\([a-z]\)_\([a-z]\)\([_.(]\)/\1.\2.\3\4/g ;
    s/_iTA_dLMux_x264/-x264-ITA-DLMux/i ;
    s/_iTA_eNG_1080p_wEB-DLMux_h_*264/-h264-ITA_ENG-1080p-WEB-DLMux/i ;
    s/_ita_web-dlmux_\(x264\|xvid\)/-\1-ITA-WEB-DLMux/i ;
    s/_ita_eng_dlmux_xvid/-XviD-ITA_ENG-DLMux/i ;
    s/.dd5_1/-DD5.1/i ;
    s/S_o_s/S.o.s./i ;
    s/-ubi/-UBi/i ;
    s/_\[tutankemule_net\]//i ;
    s/novarip/NovaRip/i ;
    s/_hdtv_x264_sub_iTA_by_zF/-x264-ENG_sub_ITA-HDTV-ZF/i ;
    s/_(720p_sub_ita)/-XviD-ENG_sub_ITA-720p/i ;
    s/_iTA_/-ITA_/i ;
    s/_eNG/_ENG/i ;
    s/1080p_nF_wEB/1080p-NF-WEB/i ;
    s/[-_\.]*itaeng/-ITA_ENG/i ;
    s/.\(dlmux\|webrip\|xvid\|divx\|x264\)/-\1/i ;
    s/webrip/WEBRip/i ;
    s/xvid/XviD/i ;
    s/divx/DivX/i ;
    s/\(ITA.*\)[-_\.]\(x264\|xvid\|divx\)/\2-\1/i ;
    s/[-_]\([a-z][a-z]\)[-_]srt$/.\1.srt/i ;
    s/[-_\.]\(srt\|mkv\|avi\|mp4\)$/.\1/i ;
#    s/.\(srt\|avi\)$/.srt/i
')\"
done

