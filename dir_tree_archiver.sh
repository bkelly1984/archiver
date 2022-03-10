#!/bin/bash

TODAY=$(/usr/bin/date +%Y%m%d)
FILENAME=$1
if [ ${FILENAME:: 2} = "./" ]; then
  FILENAME=${FILENAME: 2}
fi
if [ ${FILENAME:: 1} = "/" ]; then
  FILENAME=${FILENAME: 1}
fi
if [ ${FILENAME: -1} = "/" ]; then
  FILENAME=${FILENAME:: -1}
fi
FILENAME=$(echo $FILENAME | sed 's/\//./g')
FILENAME="${FILENAME}_DIR_TREE.${TODAY}.txt"

echo $FILENAME
find $1 -type d -printf "%TY-%Tm-%Td\t%u\t%g\t%p\n" > $2/tmp/$FILENAME

mv $2/tmp/$FILENAME $2/tar/$FILENAME
