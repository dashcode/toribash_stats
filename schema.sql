CREATE TABLE `user` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `username` varchar(32) DEFAULT NULL,
  `current_tc` int(11) DEFAULT NULL,
  `current_qi` int(11) DEFAULT NULL,
  `current_winratio` float DEFAULT NULL,
  `current_elo` float DEFAULT NULL,
  `current_posts` int(11) DEFAULT NULL,
  `current_achiev_progress` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1

CREATE TABLE `stat` (
  `user_id` int(11) NOT NULL,
  `tc` int(11) DEFAULT NULL,
  `qi` int(11) DEFAULT NULL,
  `time` datetime NOT NULL,
  `winratio` float DEFAULT NULL,
  `elo` float DEFAULT NULL,
  `posts` int(11) DEFAULT NULL,
  `achiev_progress` int(11) DEFAULT NULL,
  PRIMARY KEY (`user_id`,`time`),
  KEY `user_id_time` (`user_id`,`time`),
  CONSTRAINT `stat_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1