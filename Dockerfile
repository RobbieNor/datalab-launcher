# Load Base DataLab Image
# CACHEBUSTING: 1234567895
FROM gcr.io/cloud-datalab/datalab:local
MAINTAINER Robert Norman "mail@rjnorman.co.uk"

# Apply Minimum Required Changes to Base Image
RUN apt-get update
RUN apt-get -y install jq
RUN apt-get -y install vim

# Install R Markov Packages
RUN apt-get -y install r-base
RUN R -q -e "install.packages('ggplot2', repos='http://cran.rstudio.com/')"
RUN R -q -e "install.packages('reshape', repos='http://cran.rstudio.com/')"
RUN R -q -e "install.packages('ChannelAttribution', repos='http://cran.rstudio.com/')"
RUN R -q -e "install.packages('colorspace', repos='http://cran.rstudio.com/')"
RUN R -q -e "install.packages('optparse', repos='http://cran.rstudio.com/')"

# Install Category Flow Analysis Packages
RUN pip install py_d3

# Install Predictive Analysis Packages
RUN pip install sklearn

# Set Required Labels and Env Variables
LABEL "dll_image"="datalab"
LABEL "dll_version"="0.8.3"
ENV "dll_version"="0.8.3"
