# LaunchDarkly Exporter

This repository provides a tool for getting users up and running quickly if they are using LaunchDarkly as their feature flagging solution currently.

It will consult the LaunchDarkly API and write all the resources into a configuration format that Flipt understands.

With those configuration files you can either import the data into a Flipt instance with a backing database or serve those files from an FS (git, S3, flat files).
