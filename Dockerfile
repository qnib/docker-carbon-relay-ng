###### QNIBTerminal child
FROM qnib/terminal:fd22

RUN dnf install -y golang git-core mercurial make && \
    export GOPATH=/usr/local/ && \
    export PATH="$PATH:$GOPATH/bin" && \
    go get -d github.com/graphite-ng/carbon-relay-ng && \
    go get github.com/jteeuwen/go-bindata/... && \
    cd "$GOPATH/src/github.com/graphite-ng/carbon-relay-ng" && \
    make && \
    mv /usr/local/src/github.com/graphite-ng/carbon-relay-ng/carbon-relay-ng /usr/local/bin/ && \
    dnf remove -y make golang git-core mercurial && \
    dnf autoremove -y
ADD etc/carbon-relay-ng /etc/carbon-relay-ng
ADD etc/supervisord.d/carbon-relay-ng.ini /etc/supervisord.d/
ADD etc/consul.d/carbon-relay-ng.json /etc/consul.d/
   

