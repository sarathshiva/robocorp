package cmd

import (
	"github.com/robocorp/robo/cli/exit"
	"github.com/robocorp/robo/cli/operations/serve"
	"github.com/spf13/cobra"
)

var (
	serverPort int
)

var serveCmd = &cobra.Command{
	Use:   "serve",
	Short: "Serve tasks as local API",
	Run: func(cmd *cobra.Command, args []string) {
		if err := serve.Serve(directory, serverPort, maxLogFiles, maxLogFileSize); err != nil {
			exit.FatalExit(err)
		}
	},
}

func init() {
	serveCmd.Flags().
		IntVarP(&serverPort, "port", "p", 8080, "listening port for local server")
	serveCmd.Flags().
		IntVar(&maxLogFiles, "max_log_files", 5, "maximum number of output files to store the logs")
	serveCmd.Flags().
		StringVar(&maxLogFileSize, "max_log_file_size", "1MB", "maximum size for the log files (1MB, 500kb, ...)")
	rootCmd.AddCommand(serveCmd)
}
